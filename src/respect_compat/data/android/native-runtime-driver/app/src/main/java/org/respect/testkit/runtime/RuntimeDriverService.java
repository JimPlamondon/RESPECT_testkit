// SPDX-FileCopyrightText: 2026 Jim Plamondon
// SPDX-License-Identifier: Apache-2.0

package org.respect.testkit.runtime;

import android.app.Service;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.Message;
import android.os.Messenger;
import android.os.RemoteException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

public final class RuntimeDriverService extends Service {
    private static final String PACKAGE_NAME = "org.respect.testkit.runtime";
    private static final String PROTOCOL_VERSION = "1.0.0";
    private static final String ACTION = "org.openeel.action.xapioveripc";
    private static final int WHAT_REQUEST = 1;
    private static final int WHAT_RESPONSE = 2;
    private static final int WHAT_FLOW_EMISSION = 3;
    private static final int WHAT_FLOW_COMPLETION = 4;
    private static final int GET_STATEMENTS = 1;
    private static final int GET_STATEMENTS_FLOW = 2;
    private static final int POST_STATEMENTS = 3;
    private static final String KEY_BODY = "body";
    private static final String KEY_QUERY_PARAMS = "queryParams";
    private static final String KEY_ENDPOINT = "endpoint";
    private static final String KEY_AUTH = "auth";
    private static final String KEY_CLIENT_PACKAGE = "xapiIpcClientPackage";
    private static final String KEY_STATUS = "status";

    private final Map<String, JSONObject> statements = new LinkedHashMap<>();
    private final Set<String> voidedStatementIds = new LinkedHashSet<>();
    private final Set<Integer> activeFlows = new LinkedHashSet<>();
    private HandlerThread handlerThread;
    private Messenger messenger;
    private EventStore events;
    private String boundClientPackage = "";

    @Override
    public void onCreate() {
        super.onCreate();
        events = new EventStore(this);
        events.append(object(
                "kind", "driver_health",
                "protocol_version", PROTOCOL_VERSION,
                "package", PACKAGE_NAME));
        handlerThread = new HandlerThread("respect-runtime-driver");
        handlerThread.start();
        Handler handler = new Handler(handlerThread.getLooper(), this::handleMessage);
        messenger = new Messenger(handler);
    }

    @Override
    public IBinder onBind(Intent intent) {
        boundClientPackage = intent.getStringExtra(KEY_CLIENT_PACKAGE);
        if (boundClientPackage == null) {
            boundClientPackage = "";
        }
        events.append(object(
                "kind", "service_bound",
                "action", intent.getAction(),
                "explicit_package", intent.getPackage(),
                "client_package", boundClientPackage));
        return messenger.getBinder();
    }

    @Override
    public boolean onUnbind(Intent intent) {
        events.append(object(
                "kind", "service_unbound",
                "client_package", boundClientPackage));
        return false;
    }

    @Override
    public void onDestroy() {
        if (handlerThread != null) {
            handlerThread.quitSafely();
        }
        super.onDestroy();
    }

    private boolean handleMessage(Message message) {
        if (message.what == WHAT_FLOW_COMPLETION) {
            activeFlows.remove(message.arg1);
            events.append(object(
                    "kind", "flow_completed",
                    "request_id", message.arg1));
            return true;
        }
        if (message.what != WHAT_REQUEST) {
            return false;
        }
        Bundle data = message.getData();
        String clientPackage = data.getString(KEY_CLIENT_PACKAGE, boundClientPackage);
        JSONObject queryParams = bundleToJson(data.getBundle(KEY_QUERY_PARAMS));
        JSONObject requestEvent = object(
                "kind", "request",
                "what", message.what,
                "request_id", message.arg1,
                "operation", message.arg2,
                "endpoint", data.getString(KEY_ENDPOINT),
                "auth", data.getString(KEY_AUTH),
                "client_package", clientPackage,
                "has_reply_to", message.replyTo != null);
        if (data.containsKey(KEY_BODY)) {
            put(requestEvent, "body", data.getString(KEY_BODY));
        }
        if (queryParams.length() > 0) {
            put(requestEvent, "query_params", queryParams);
        }
        events.append(requestEvent);
        try {
            if (message.arg2 == POST_STATEMENTS) {
                handlePost(message, data);
            } else if (message.arg2 == GET_STATEMENTS) {
                handleGet(message, queryParams, false);
            } else if (message.arg2 == GET_STATEMENTS_FLOW) {
                activeFlows.add(message.arg1);
                handleGet(message, queryParams, true);
            } else {
                send(message, WHAT_RESPONSE, 400, null);
            }
        } catch (Exception error) {
            send(message, WHAT_RESPONSE, 500, null);
        }
        return true;
    }

    private void handlePost(Message message, Bundle data) throws JSONException {
        JSONArray incoming = new JSONArray(data.getString(KEY_BODY, "[]"));
        JSONArray identifiers = new JSONArray();
        int status = 200;
        for (int index = 0; index < incoming.length(); index++) {
            JSONObject statement = incoming.getJSONObject(index);
            String identifier = statement.optString("id", UUID.randomUUID().toString());
            statement.put("id", identifier);
            JSONObject existing = statements.get(identifier);
            if (existing != null && !sameJson(existing, statement)) {
                status = 409;
                break;
            }
            if (existing == null) {
                statements.put(identifier, new JSONObject(statement.toString()));
            }
            JSONObject verb = statement.optJSONObject("verb");
            JSONObject object = statement.optJSONObject("object");
            if (verb != null
                    && "http://adlnet.gov/expapi/verbs/voided".equals(verb.optString("id"))
                    && object != null
                    && "StatementRef".equals(object.optString("objectType"))) {
                voidedStatementIds.add(object.optString("id"));
            }
            identifiers.put(identifier);
        }
        send(message, WHAT_RESPONSE, status, status == 200 ? identifiers.toString() : null);
    }

    private void handleGet(Message message, JSONObject queryParams, boolean flow) {
        JSONArray selected = selectStatements(queryParams);
        JSONObject result = object("statements", selected, "more", JSONObject.NULL);
        send(
                message,
                flow ? WHAT_FLOW_EMISSION : WHAT_RESPONSE,
                200,
                result.toString());
    }

    private JSONArray selectStatements(JSONObject queryParams) {
        JSONArray selected = new JSONArray();
        String statementId = first(queryParams, "statementId");
        String voidedStatementId = first(queryParams, "voidedStatementId");
        if (statementId != null) {
            JSONObject statement = statements.get(statementId);
            if (statement != null && !voidedStatementIds.contains(statementId)) {
                selected.put(statement);
            }
            return selected;
        }
        if (voidedStatementId != null) {
            JSONObject statement = statements.get(voidedStatementId);
            if (statement != null && voidedStatementIds.contains(voidedStatementId)) {
                selected.put(statement);
            }
            return selected;
        }
        String verb = first(queryParams, "verb");
        String activity = first(queryParams, "activity");
        int limit = parsePositiveInt(first(queryParams, "limit"), Integer.MAX_VALUE);
        for (Map.Entry<String, JSONObject> entry : statements.entrySet()) {
            if (selected.length() >= limit || voidedStatementIds.contains(entry.getKey())) {
                continue;
            }
            JSONObject statement = entry.getValue();
            JSONObject statementVerb = statement.optJSONObject("verb");
            JSONObject statementObject = statement.optJSONObject("object");
            if (verb != null
                    && (statementVerb == null || !verb.equals(statementVerb.optString("id")))) {
                continue;
            }
            if (activity != null
                    && (statementObject == null || !activity.equals(statementObject.optString("id")))) {
                continue;
            }
            selected.put(statement);
        }
        return selected;
    }

    private void send(Message request, int what, int status, String body) {
        if (request.replyTo == null) {
            return;
        }
        Message response = Message.obtain();
        response.what = what;
        response.arg1 = request.arg1;
        Bundle responseData = new Bundle();
        responseData.putInt(KEY_STATUS, status);
        if (body != null) {
            responseData.putString(KEY_BODY, body);
        }
        response.setData(responseData);
        events.append(object(
                "kind", what == WHAT_FLOW_EMISSION ? "flow_emission" : "response",
                "request_id", request.arg1,
                "status", status,
                "body", body));
        try {
            request.replyTo.send(response);
        } catch (RemoteException error) {
            events.append(object(
                    "kind", "reply_failed",
                    "request_id", request.arg1,
                    "error", error.getClass().getSimpleName()));
        }
    }

    private static JSONObject bundleToJson(Bundle bundle) {
        JSONObject result = new JSONObject();
        if (bundle == null) {
            return result;
        }
        for (String key : bundle.keySet()) {
            Object value = bundle.get(key);
            JSONArray values = new JSONArray();
            if (value instanceof String[]) {
                for (String item : (String[]) value) {
                    values.put(item);
                }
            } else if (value instanceof String) {
                values.put(value);
            }
            put(result, key, values);
        }
        return result;
    }

    private static String first(JSONObject object, String key) {
        JSONArray values = object.optJSONArray(key);
        return values != null && values.length() > 0 ? values.optString(0, null) : null;
    }

    private static int parsePositiveInt(String value, int fallback) {
        if (value == null) {
            return fallback;
        }
        try {
            int parsed = Integer.parseInt(value);
            return parsed > 0 ? parsed : fallback;
        } catch (NumberFormatException error) {
            return fallback;
        }
    }

    private static boolean sameJson(JSONObject left, JSONObject right) {
        return left.toString().equals(right.toString());
    }

    private static JSONObject object(Object... values) {
        JSONObject object = new JSONObject();
        for (int index = 0; index + 1 < values.length; index += 2) {
            put(object, String.valueOf(values[index]), values[index + 1]);
        }
        return object;
    }

    private static void put(JSONObject object, String key, Object value) {
        try {
            object.put(key, value == null ? JSONObject.NULL : value);
        } catch (JSONException error) {
            throw new IllegalStateException(error);
        }
    }
}

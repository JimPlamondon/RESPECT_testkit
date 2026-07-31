// SPDX-FileCopyrightText: 2026 Jim Plamondon
// SPDX-License-Identifier: Apache-2.0

package org.respect.testkit.gesture;

import android.app.Activity;
import android.app.Instrumentation;
import android.app.UiAutomation;
import android.content.Context;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Base64;
import android.util.DisplayMetrics;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.json.JSONArray;
import org.json.JSONObject;

public final class GestureInstrumentation extends Instrumentation {
    private static final String FORMAT_VERSION = "1.0.0";
    private Bundle arguments;

    @Override
    public void onCreate(Bundle suppliedArguments) {
        super.onCreate(suppliedArguments);
        arguments = suppliedArguments;
        start();
    }

    @Override
    public void onStart() {
        JSONObject receipt = new JSONObject();
        int resultCode = Activity.RESULT_OK;
        try {
            String encoded = arguments == null ? null : arguments.getString("stroke");
            if (encoded == null || encoded.length() > 64_000) {
                throw new IllegalArgumentException("bounded stroke payload is missing");
            }
            JSONObject payload = new JSONObject(new String(
                    Base64.decode(encoded, Base64.URL_SAFE | Base64.NO_WRAP),
                    StandardCharsets.UTF_8));
            copyBinding(payload, receipt);
            if (!FORMAT_VERSION.equals(payload.optString("format_version"))) {
                throw new IllegalArgumentException("stroke payload version is unsupported");
            }

            UiAutomation automation = getUiAutomation(
                    UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
            AccessibilityNodeInfo root = waitForRoot(automation);
            String expectedPackage = payload.getString("canapp_package");
            String foregroundPackage = String.valueOf(root.getPackageName());
            receipt.put("foreground_package", foregroundPackage);
            if (!expectedPackage.equals(foregroundPackage)) {
                throw new IllegalStateException("foreground package changed before stroke");
            }

            Rect bounds = resolveBounds(root, payload.getJSONObject("anchor"));
            if (bounds.width() <= 0 || bounds.height() <= 0) {
                throw new IllegalStateException("stroke anchor has empty bounds");
            }
            receipt.put("resolved_bounds", rectJson(bounds));

            DisplayMetrics metrics = new DisplayMetrics();
            WindowManager windows =
                    (WindowManager) getContext().getSystemService(Context.WINDOW_SERVICE);
            windows.getDefaultDisplay().getRealMetrics(metrics);
            receipt.put("display_width", metrics.widthPixels);
            receipt.put("display_height", metrics.heightPixels);
            receipt.put("display_density_dpi", metrics.densityDpi);
            receipt.put("display_rotation", windows.getDefaultDisplay().getRotation());

            JSONArray normalized = payload.getJSONArray("points");
            JSONArray resolved = resolvePoints(normalized, bounds);
            receipt.put("resolved_points", resolved);
            long started = SystemClock.uptimeMillis();
            injectStroke(automation, resolved, started);
            receipt.put("started_uptime_ms", started);
            receipt.put("finished_uptime_ms", SystemClock.uptimeMillis());
            receipt.put("kind", "stroke_injected");
            receipt.put("success", true);
        } catch (Throwable error) {
            resultCode = Activity.RESULT_CANCELED;
            put(receipt, "kind", "stroke_injected");
            put(receipt, "success", false);
            put(receipt, "error_type", error.getClass().getSimpleName());
        }
        appendReceipt(receipt);
        Bundle result = new Bundle();
        result.putString("receipt_sha256_input", receipt.toString());
        finish(resultCode, result);
    }

    private static void copyBinding(JSONObject payload, JSONObject receipt) throws Exception {
        receipt.put("action_index", payload.getInt("action_index"));
        receipt.put("action_sha256", payload.getString("action_sha256"));
        receipt.put("scenario_nonce", payload.getString("scenario_nonce"));
        receipt.put("canapp_package", payload.getString("canapp_package"));
    }

    private static AccessibilityNodeInfo waitForRoot(UiAutomation automation) {
        for (int attempt = 0; attempt < 50; attempt++) {
            AccessibilityNodeInfo root = automation.getRootInActiveWindow();
            if (root != null) {
                return root;
            }
            SystemClock.sleep(100);
        }
        throw new IllegalStateException("foreground accessibility root is unavailable");
    }

    private static Rect resolveBounds(
            AccessibilityNodeInfo root,
            JSONObject anchor) throws Exception {
        if ("foreground_window".equals(anchor.getString("type"))) {
            Rect bounds = new Rect();
            root.getBoundsInScreen(bounds);
            return bounds;
        }
        JSONObject selector = anchor.getJSONObject("selector");
        List<AccessibilityNodeInfo> matches = new ArrayList<>();
        collectMatches(root, selector, matches);
        if (matches.size() != 1) {
            throw new IllegalStateException(
                    "element anchor must resolve to exactly one accessibility node");
        }
        Rect bounds = new Rect();
        matches.get(0).getBoundsInScreen(bounds);
        return bounds;
    }

    private static void collectMatches(
            AccessibilityNodeInfo node,
            JSONObject selector,
            List<AccessibilityNodeInfo> matches) {
        if (matches(node, selector)) {
            matches.add(node);
        }
        for (int index = 0; index < node.getChildCount(); index++) {
            AccessibilityNodeInfo child = node.getChild(index);
            if (child != null) {
                collectMatches(child, selector, matches);
            }
        }
    }

    private static boolean matches(
            AccessibilityNodeInfo node,
            JSONObject selector) {
        return matchesValue(
                        selector,
                        "resource_id",
                        node.getViewIdResourceName())
                && matchesValue(
                        selector,
                        "class_name",
                        node.getClassName())
                && matchesValue(selector, "text", node.getText())
                && matchesValue(
                        selector,
                        "content_description",
                        node.getContentDescription());
    }

    private static boolean matchesValue(
            JSONObject selector,
            String key,
            Object actual) {
        return !selector.has(key)
                || selector.optString(key).contentEquals(
                        actual == null ? "" : String.valueOf(actual));
    }

    private static JSONArray resolvePoints(JSONArray points, Rect bounds)
            throws Exception {
        JSONArray result = new JSONArray();
        for (int index = 0; index < points.length(); index++) {
            JSONObject point = points.getJSONObject(index);
            int x = bounds.left + Math.round(
                    (point.getInt("x") / 10_000.0f) * Math.max(0, bounds.width() - 1));
            int y = bounds.top + Math.round(
                    (point.getInt("y") / 10_000.0f) * Math.max(0, bounds.height() - 1));
            if (!bounds.contains(x, y)) {
                throw new IllegalArgumentException("resolved stroke point is outside anchor");
            }
            result.put(new JSONObject()
                    .put("x", x)
                    .put("y", y)
                    .put("at_ms", point.getInt("at_ms")));
        }
        return result;
    }

    private static void injectStroke(
            UiAutomation automation,
            JSONArray points,
            long downTime) throws Exception {
        JSONObject first = points.getJSONObject(0);
        float currentX = first.getInt("x");
        float currentY = first.getInt("y");
        boolean down = false;
        try {
            inject(
                    automation,
                    downTime,
                    downTime,
                    MotionEvent.ACTION_DOWN,
                    currentX,
                    currentY);
            down = true;
            for (int index = 1; index < points.length(); index++) {
                JSONObject point = points.getJSONObject(index);
                long targetTime = downTime + point.getInt("at_ms");
                long delay = targetTime - SystemClock.uptimeMillis();
                if (delay > 0) {
                    SystemClock.sleep(delay);
                }
                currentX = point.getInt("x");
                currentY = point.getInt("y");
                inject(
                        automation,
                        downTime,
                        SystemClock.uptimeMillis(),
                        MotionEvent.ACTION_MOVE,
                        currentX,
                        currentY);
            }
            inject(
                    automation,
                    downTime,
                    SystemClock.uptimeMillis(),
                    MotionEvent.ACTION_UP,
                    currentX,
                    currentY);
            down = false;
        } finally {
            if (down) {
                inject(
                        automation,
                        downTime,
                        SystemClock.uptimeMillis(),
                        MotionEvent.ACTION_CANCEL,
                        currentX,
                        currentY);
            }
        }
    }

    private static void inject(
            UiAutomation automation,
            long downTime,
            long eventTime,
            int action,
            float x,
            float y) {
        MotionEvent event = MotionEvent.obtain(
                downTime,
                eventTime,
                action,
                x,
                y,
                0);
        event.setSource(InputDevice.SOURCE_TOUCHSCREEN);
        try {
            if (!automation.injectInputEvent(event, true)) {
                throw new IllegalStateException("motion event injection failed");
            }
        } finally {
            event.recycle();
        }
    }

    private static JSONObject rectJson(Rect bounds) throws Exception {
        return new JSONObject()
                .put("left", bounds.left)
                .put("top", bounds.top)
                .put("right", bounds.right)
                .put("bottom", bounds.bottom);
    }

    private void appendReceipt(JSONObject receipt) {
        File destination = new File(
                getContext().getFilesDir(),
                "gesture-events.jsonl");
        byte[] line = (receipt.toString() + "\n").getBytes(StandardCharsets.UTF_8);
        try (FileOutputStream output = new FileOutputStream(destination, true)) {
            output.write(line);
            output.getFD().sync();
        } catch (Exception error) {
            throw new IllegalStateException("gesture receipt could not be persisted", error);
        }
    }

    private static void put(JSONObject object, String key, Object value) {
        try {
            object.put(key, value);
        } catch (Exception ignored) {
            // A best-effort failure receipt must not mask the original failure.
        }
    }
}

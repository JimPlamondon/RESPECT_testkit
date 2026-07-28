// SPDX-FileCopyrightText: 2026 Jim Plamondon
// SPDX-License-Identifier: Apache-2.0

package org.respect.testkit.runtime;

import android.content.Context;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicLong;
import org.json.JSONException;
import org.json.JSONObject;

final class EventStore {
    private final File eventFile;
    private final AtomicLong sequence = new AtomicLong(1);

    EventStore(Context context) {
        eventFile = new File(context.getFilesDir(), "events.jsonl");
    }

    synchronized void append(JSONObject event) {
        try {
            event.put("sequence", sequence.getAndIncrement());
            byte[] line = (event.toString() + "\n").getBytes(StandardCharsets.UTF_8);
            try (FileOutputStream output = new FileOutputStream(eventFile, true)) {
                output.write(line);
                output.getFD().sync();
            }
        } catch (IOException | JSONException error) {
            throw new IllegalStateException("Unable to persist runtime-driver evidence", error);
        }
    }
}

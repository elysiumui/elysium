package dev.elysium.pycharm

import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory
import java.awt.BorderLayout
import java.awt.Color
import java.awt.Dimension
import java.awt.Font
import java.awt.Graphics
import java.awt.Graphics2D
import java.awt.RenderingHints
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.Socket
import java.net.InetSocketAddress
import javax.swing.*
import org.json.JSONObject

/** Live inspector — frame histogram + hook traffic log.
 *
 *  The runtime exposes a small JSON-over-TCP stats endpoint on a
 *  per-session port (default 11434) when the app is started with
 *  ELYSIUM_INSPECTOR=1. Each tick gives us:
 *    { frame_ms: [..256 samples..],
 *      paint_ms: float, composite_ms: float, swap_ms: float,
 *      hooks_fired: [{ name, dt_ms, ts }, ...] }
 *  We render the timing as a sparkline and the hook log as a tail.
 */
class InspectorToolWindowFactory : ToolWindowFactory {

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val histogram = HistogramPanel()
        val statusLabel = JLabel("Connecting…").apply {
            border = BorderFactory.createEmptyBorder(4, 8, 4, 8)
        }
        val hookLog = JTextArea().apply {
            isEditable = false
            font = Font(Font.MONOSPACED, Font.PLAIN, 11)
        }
        val panel = JPanel(BorderLayout()).apply {
            add(statusLabel, BorderLayout.NORTH)
            add(histogram,   BorderLayout.CENTER)
            add(JScrollPane(hookLog).apply {
                preferredSize = Dimension(0, 140)
            }, BorderLayout.SOUTH)
        }

        val poller = StatsPoller(statusLabel, histogram, hookLog)
        Timer(200) { poller.tick() }.start()

        val content = ContentFactory.getInstance().createContent(panel, "", false)
        toolWindow.contentManager.addContent(content)
    }
}

private class HistogramPanel : JPanel() {
    var samples: FloatArray = FloatArray(0)
    var labels:  Triple<Float, Float, Float> = Triple(0f, 0f, 0f)  // paint, composite, swap

    init { background = Color(28, 28, 32) }

    override fun paintComponent(g: Graphics) {
        super.paintComponent(g)
        val g2 = g as Graphics2D
        g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING,
                            RenderingHints.VALUE_ANTIALIAS_ON)
        if (samples.isEmpty()) return
        val w = width.toFloat()
        val h = height.toFloat()
        val max = (samples.max() ?: 16.66f).coerceAtLeast(16.66f)
        val barW = w / samples.size
        for ((i, ms) in samples.withIndex()) {
            val t = (ms / max).coerceIn(0f, 1f)
            val barH = h * t
            g2.color = when {
                ms > 33.3f -> Color(255, 90, 90)
                ms > 16.7f -> Color(255, 200, 0)
                else       -> Color(120, 220, 160)
            }
            g2.fillRect((i * barW).toInt(), (h - barH).toInt(),
                        barW.toInt().coerceAtLeast(1), barH.toInt())
        }
        // 16.67ms baseline.
        g2.color = Color(255, 255, 255, 80)
        val baseY = (h - (h * 16.667f / max)).toInt()
        g2.drawLine(0, baseY, w.toInt(), baseY)
        g2.color = Color.WHITE
        g2.font = Font(Font.MONOSPACED, Font.PLAIN, 10)
        g2.drawString("60Hz · paint ${"%.1f".format(labels.first)}ms · " +
                      "comp ${"%.1f".format(labels.second)}ms · " +
                      "swap ${"%.1f".format(labels.third)}ms",
                      8, baseY - 4)
    }
}

private class StatsPoller(
    val status: JLabel,
    val histogram: HistogramPanel,
    val hookLog: JTextArea,
) {
    private var socket: Socket? = null
    private var reader: BufferedReader? = null
    private var writer: OutputStreamWriter? = null
    private val host = System.getenv("ELYSIUM_INSPECTOR_HOST") ?: "127.0.0.1"
    private val port = System.getenv("ELYSIUM_INSPECTOR_PORT")?.toIntOrNull() ?: 11434

    fun tick() {
        try {
            ensureConnected()
            val r = reader ?: return
            val w = writer ?: return
            w.write("get_stats\n"); w.flush()
            val line = r.readLine() ?: run { reconnect(); return }
            val doc = JSONObject(line)
            val arr = doc.getJSONArray("frame_ms")
            histogram.samples = FloatArray(arr.length()) { arr.getDouble(it).toFloat() }
            histogram.labels  = Triple(
                doc.optDouble("paint_ms", 0.0).toFloat(),
                doc.optDouble("composite_ms", 0.0).toFloat(),
                doc.optDouble("swap_ms", 0.0).toFloat(),
            )
            histogram.repaint()
            status.text = "Connected · ${arr.length()} samples"
            val hooks = doc.optJSONArray("hooks_fired") ?: return
            val tail = StringBuilder(hookLog.text)
            for (i in 0 until hooks.length()) {
                val h = hooks.getJSONObject(i)
                tail.append("[%.1fms]  %s%n".format(
                    h.optDouble("dt_ms", 0.0), h.optString("name", "?")))
            }
            // Keep last ~80 lines.
            val all = tail.toString().lines()
            hookLog.text = all.takeLast(80).joinToString("\n")
        } catch (e: Exception) {
            status.text = "(no app listening on $host:$port — start your app with " +
                          "ELYSIUM_INSPECTOR=1)"
            reconnect()
        }
    }

    private fun ensureConnected() {
        if (socket?.isConnected == true && !socket!!.isClosed) return
        val s = Socket()
        s.connect(InetSocketAddress(host, port), 250)
        socket = s
        reader = BufferedReader(InputStreamReader(s.getInputStream()))
        writer = OutputStreamWriter(s.getOutputStream())
    }

    private fun reconnect() {
        try { socket?.close() } catch (_: Exception) {}
        socket = null; reader = null; writer = null
    }
}

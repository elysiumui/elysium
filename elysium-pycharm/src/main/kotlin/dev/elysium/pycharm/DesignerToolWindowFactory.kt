package dev.elysium.pycharm

import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.openapi.fileChooser.FileChooserFactory
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.openapi.vfs.newvfs.BulkFileListener
import com.intellij.openapi.vfs.newvfs.events.VFileEvent
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory
import com.intellij.util.messages.MessageBusConnection
import java.awt.BorderLayout
import java.awt.Color
import java.awt.Dimension
import java.awt.Graphics
import java.awt.Image
import java.awt.image.BufferedImage
import java.io.ByteArrayInputStream
import java.io.File
import javax.imageio.ImageIO
import javax.swing.*

/** Embedded Designer companion panel.
 *
 *  Cross-process window reparenting on macOS / Windows / Wayland is
 *  fragile and inconsistent, so we deliver the same value a different
 *  way: this panel hosts a live preview of the current skin rendered
 *  via the framework's `paint_skin_png` helper, plus quick actions to
 *  launch the standalone Designer and to scaffold missing handlers.
 *
 *  The preview refreshes whenever a file under the chosen `.esk/`
 *  directory changes (VFS-listener driven, no polling) so the dev
 *  loop is: edit document.json → save → see the new look here.
 */
class DesignerToolWindowFactory : ToolWindowFactory {
    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val panel = DesignerCompanionPanel(project)
        val content = ContentFactory.getInstance().createContent(panel, "", false)
        toolWindow.contentManager.addContent(content)
    }
}

private class DesignerCompanionPanel(val project: Project) : JPanel(BorderLayout()) {
    private val preview = PreviewPanel()
    private val pathLabel = JLabel("No skin selected.")
    private var skinPath: String? = null
    private var bus: MessageBusConnection? = null

    init {
        background = Color(36, 36, 40)

        val toolbar = JPanel().apply {
            background = Color(28, 28, 32)
            add(JButton("Open .esk…").apply { addActionListener { pickSkin() } })
            add(JButton("Launch Designer").apply { addActionListener { launchDesigner() } })
            add(JButton("Scaffold handlers").apply {
                addActionListener { scaffoldHandlers() }
            })
            add(JButton("Re-render preview").apply { addActionListener { refresh() } })
        }
        add(toolbar, BorderLayout.NORTH)
        add(JScrollPane(preview), BorderLayout.CENTER)
        add(pathLabel.apply {
            border = BorderFactory.createEmptyBorder(4, 8, 4, 8)
            foreground = Color.LIGHT_GRAY
        }, BorderLayout.SOUTH)
    }

    private fun pickSkin() {
        val desc = FileChooserDescriptorFactory.createSingleFolderDescriptor()
        val chooser = FileChooserFactory.getInstance().createFileChooser(desc, project, null)
        val files = chooser.choose(project)
        if (files.isEmpty()) return
        val file = files[0]
        if (!file.findChild("document.json")?.exists().let { it == true }) {
            JOptionPane.showMessageDialog(this,
                "Pick a directory that contains document.json (a .esk skin).",
                "Designer", JOptionPane.WARNING_MESSAGE)
            return
        }
        skinPath = file.path
        pathLabel.text = file.path
        watch(file)
        refresh()
    }

    private fun watch(skin: VirtualFile) {
        bus?.disconnect()
        bus = project.messageBus.connect()
        bus!!.subscribe(com.intellij.openapi.vfs.newvfs.BulkFileListener.TOPIC,
            object : BulkFileListener {
                override fun after(events: MutableList<out VFileEvent>) {
                    val prefix = skin.path + "/"
                    if (events.any { it.path == skin.path || it.path.startsWith(prefix) }) {
                        SwingUtilities.invokeLater { refresh() }
                    }
                }
            })
    }

    private fun refresh() {
        val path = skinPath ?: return
        try {
            val py = ProcessBuilder("python", "-c", """
                import sys, base64
                from elysium.skin import load_skin
                from elysium.render.preview import paint_skin_png
                png = paint_skin_png(${"\"" + path.replace("\"", "\\\"") + "\""})
                sys.stdout.buffer.write(png)
            """.trimIndent())
            py.redirectErrorStream(false)
            val proc = py.start()
            val bytes = proc.inputStream.readBytes()
            proc.waitFor()
            if (bytes.isEmpty()) {
                preview.image = null; preview.repaint(); return
            }
            preview.image = ImageIO.read(ByteArrayInputStream(bytes))
            preview.repaint()
        } catch (e: Exception) {
            JOptionPane.showMessageDialog(this,
                "Preview render failed: ${e.message}",
                "Designer", JOptionPane.ERROR_MESSAGE)
        }
    }

    private fun launchDesigner() {
        val path = skinPath ?: return
        try {
            ProcessBuilder("elysium-designer", path).start()
        } catch (e: Exception) {
            JOptionPane.showMessageDialog(this,
                "Failed to launch elysium-designer: ${e.message}",
                "Designer", JOptionPane.ERROR_MESSAGE)
        }
    }

    private fun scaffoldHandlers() {
        val path = skinPath ?: return
        try {
            val cmd = listOf("python", "-c", """
                from pathlib import Path
                from elysium import codelink
                from elysium.skin import load_skin
                import json
                doc = json.loads(Path("$path/document.json").read_text())
                def hooks(node):
                    out = []
                    for h in (node.get("hooks") or []):
                        if h.get("name"): out.append(h["name"])
                    for c in (node.get("children") or []): out += hooks(c)
                    return out
                names = hooks(doc.get("root", {}))
                target = Path("$path").parent / (Path("$path").stem + ".py")
                created = 0
                idx = codelink.index_handlers(target, known_hooks=names)
                for n in names:
                    if n not in idx:
                        codelink.scaffold_handler(target, n); created += 1
                print(f"scaffolded {created} handlers → {target}")
            """.trimIndent())
            val proc = ProcessBuilder(cmd).redirectErrorStream(true).start()
            val text = proc.inputStream.bufferedReader().readText()
            proc.waitFor()
            JOptionPane.showMessageDialog(this, text, "Code Link",
                                          JOptionPane.INFORMATION_MESSAGE)
        } catch (e: Exception) {
            JOptionPane.showMessageDialog(this,
                "Scaffold failed: ${e.message}",
                "Code Link", JOptionPane.ERROR_MESSAGE)
        }
    }
}

private class PreviewPanel : JPanel() {
    var image: BufferedImage? = null

    init {
        background = Color(20, 20, 24)
        preferredSize = Dimension(800, 600)
    }

    override fun paintComponent(g: Graphics) {
        super.paintComponent(g)
        val img = image ?: return
        val iw = img.width.toDouble()
        val ih = img.height.toDouble()
        val s = minOf(width / iw, height / ih).coerceAtMost(1.0)
        val w = (iw * s).toInt()
        val h = (ih * s).toInt()
        val x = (width - w) / 2
        val y = (height - h) / 2
        g.drawImage(img, x, y, w, h, this)
    }
}

package dev.elysium.pycharm.actions

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.ui.Messages

/** Editor → Designer jump.
 *
 *  Reads the word under the caret, looks for a string-literal `"hook"`
 *  on the same line, then spawns `elysium-designer` with
 *  `ELYSIUM_SELECT_HOOK=<hook>` so the Designer auto-selects the
 *  matching placement.
 */
class OpenInDesignerAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val editor = e.getData(CommonDataKeys.EDITOR) ?: return
        val project = e.project ?: return
        val caret = editor.caretModel.currentCaret
        val line = editor.document.getLineNumber(caret.offset)
        val text = editor.document.getText(
            com.intellij.openapi.util.TextRange(
                editor.document.getLineStartOffset(line),
                editor.document.getLineEndOffset(line),
            ),
        )
        val hook = Regex("""(?:win|window)\["([A-Za-z0-9_.-]+)"]""")
            .find(text)?.groupValues?.get(1)
            ?: Regex("""@(?:win|window)\.on\(\s*["']([A-Za-z0-9_.-]+)["']\s*\)""")
                .find(text)?.groupValues?.get(1)
        if (hook == null) {
            Messages.showInfoMessage(project,
                "No Elysium hook reference on this line.",
                "Open in Designer")
            return
        }
        try {
            val skin = project.basePath ?: ""
            val pb = ProcessBuilder("elysium-designer", skin)
            pb.environment()["ELYSIUM_SELECT_HOOK"] = hook
            pb.start()
        } catch (ex: Exception) {
            Messages.showErrorDialog(project,
                "Failed to launch elysium-designer: ${ex.message}",
                "Open in Designer")
        }
    }
}

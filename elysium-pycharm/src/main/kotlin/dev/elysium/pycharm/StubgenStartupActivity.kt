package dev.elysium.pycharm

import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.ProjectActivity
import com.intellij.openapi.vfs.newvfs.BulkFileListener
import com.intellij.openapi.vfs.newvfs.events.VFileEvent
import com.intellij.util.messages.MessageBusConnection
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Re-generate `.pyi` stubs for every skin in the project whenever
 *  the user saves a `.esk/document.json` (or sibling). PyCharm picks
 *  up the new stubs on its next type-resolution pass — no plugin
 *  restart required.
 */
class StubgenStartupActivity : ProjectActivity {
    override suspend fun execute(project: Project) = withContext(Dispatchers.IO) {
        // Initial sweep so existing skins get stubs even without an edit.
        regenerate(project)
        val bus: MessageBusConnection = project.messageBus.connect()
        bus.subscribe(BulkFileListener.TOPIC, object : BulkFileListener {
            override fun after(events: MutableList<out VFileEvent>) {
                if (events.any { it.path.endsWith("/document.json")
                              || it.path.endsWith("/manifest.json")
                              || it.path.endsWith("/hooks.json") }) {
                    regenerate(project)
                }
            }
        })
    }

    private fun regenerate(project: Project) {
        val root = project.basePath ?: return
        try {
            ProcessBuilder("python", "-c", """
                from elysium.stubgen import generate_for_workspace
                stubs = generate_for_workspace(${'"'}$root${'"'},
                                                output_dir=${'"'}$root/.elysium/stubs${'"'})
                print(f'regenerated {len(stubs)} stub(s)')
            """.trimIndent())
                .redirectErrorStream(true)
                .start()
                .waitFor()
        } catch (_: Exception) {
            // Best-effort: missing `elysium` install is fine — user might
            // be opening the project in a fresh venv.
        }
    }
}

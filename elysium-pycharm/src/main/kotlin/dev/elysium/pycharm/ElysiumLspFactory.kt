package dev.elysium.pycharm

import com.intellij.openapi.project.Project
import com.redhat.devtools.lsp4ij.LanguageServerFactory
import com.redhat.devtools.lsp4ij.client.LanguageClientImpl
import com.redhat.devtools.lsp4ij.server.ProcessStreamConnectionProvider
import com.redhat.devtools.lsp4ij.server.StreamConnectionProvider

/** Spawns the shared `elysium-lsp` Python sidecar over stdio.
 *
 *  The same binary backs the VS Code / Helix / Zed integrations, so
 *  every feature lives in one Python codebase; this plugin is glue
 *  plus PyCharm-specific UI (tool windows, run config, code lenses).
 */
class ElysiumLspFactory : LanguageServerFactory {
    override fun createConnectionProvider(project: Project): StreamConnectionProvider {
        val cmd = listOf(elysiumLspBinary())
        val cwd = project.basePath
        val provider = ProcessStreamConnectionProvider(cmd, cwd)
        provider.userEnvironmentVariables =
            mapOf("ELYSIUM_FROM_PYCHARM" to "1")
        return provider
    }

    override fun createLanguageClient(project: Project): LanguageClientImpl =
        LanguageClientImpl(project)

    private fun elysiumLspBinary(): String {
        // Allow per-project override via Settings → Elysium UI.
        val override = System.getenv("ELYSIUM_LSP")
        if (!override.isNullOrEmpty()) return override
        return "elysium-lsp"
    }
}

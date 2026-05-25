import * as vscode from "vscode";
import {
  LanguageClient, LanguageClientOptions, ServerOptions, TransportKind,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

export function activate(context: vscode.ExtensionContext) {
  const cmd = vscode.workspace
    .getConfiguration("elysium")
    .get<string>("lspPath", "elysium-lsp");

  const serverOptions: ServerOptions = {
    command: cmd,
    transport: TransportKind.stdio,
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: "file", language: "python" },
      { scheme: "file", pattern: "**/*.esk/document.json" },
    ],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher(
        "**/*.esk/{document.json,manifest.json,hooks.json}",
      ),
    },
  };

  client = new LanguageClient(
    "elysium",
    "Elysium UI",
    serverOptions,
    clientOptions,
  );
  context.subscriptions.push(client);
  client.start();

  // Code Link command — invoked from the LSP code-lens on @win.on(...).
  // Spawns `elysium-designer` pointed at the skin that owns the hook,
  // passing the hook id so the Designer can pre-select that placement.
  context.subscriptions.push(
    vscode.commands.registerCommand(
      "elysium.openInDesigner",
      async (hook: string, skinPath: string) => {
        if (!skinPath) {
          vscode.window.showWarningMessage(
            `No skin in this workspace declares hook '${hook}'`);
          return;
        }
        const term = vscode.window.createTerminal({
          name: "Elysium Designer",
          env: { ELYSIUM_SELECT_HOOK: hook },
        });
        term.show(false);
        term.sendText(`elysium-designer "${skinPath}"`, true);
      },
    ),
  );
}

export function deactivate(): Thenable<void> | undefined {
  return client ? client.stop() : undefined;
}

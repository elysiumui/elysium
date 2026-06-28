use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Message {
    Hello {
        client: String,
        token: String,
        protocol_version: u32,
    },
    SkinChanged {
        path: String,
        sha256: String,
    },
    NodePatch {
        node_id: u32,
        patch: serde_json::Value,
    },
    HookRenamed {
        old: String,
        new: String,
    },
    PythonModuleReloaded {
        module: String,
    },
    SubscribeScene,
    Disconnect,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Ack {
    pub ok: bool,
    pub message: Option<String>,
    pub reload_ms: Option<u32>,
    pub warnings: Vec<String>,
}

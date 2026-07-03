use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum HookKind {
    Event {
        #[serde(default)]
        events: Vec<String>,
    },
    Text,
    Image,
    Value {
        #[serde(default)]
        range: Option<[f64; 2]>,
    },
    State {
        states: Vec<String>,
    },
    Slot,
    Style,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Hook {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub node_id: u32,
    #[serde(flatten)]
    pub kind: HookKind,
}

impl Hook {
    pub fn id(&self) -> u32 {
        self.node_id
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct HookRegistry {
    #[serde(flatten)]
    pub by_name: HashMap<String, Hook>,
}

impl HookRegistry {
    pub fn insert(&mut self, h: Hook) {
        self.by_name.insert(h.name.clone(), h);
    }
    pub fn get(&self, key: &str) -> Option<&Hook> {
        self.by_name.get(key)
    }
    pub fn len(&self) -> usize {
        self.by_name.len()
    }
    pub fn is_empty(&self) -> bool {
        self.by_name.is_empty()
    }
    pub fn iter(&self) -> impl Iterator<Item = (&String, &Hook)> {
        self.by_name.iter()
    }
}

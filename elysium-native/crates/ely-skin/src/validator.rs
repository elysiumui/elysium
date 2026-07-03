//! Schema validation for `.esk` documents. Phase 1.3 wires a JSON Schema
//! validator against `schemas/esk-1.0.json`; this stub keeps the contract
//! visible to downstream crates.

use thiserror::Error;

#[derive(Debug, Error)]
pub enum ValidationError {
    #[error("schema violation: {0}")]
    Schema(String),
}

pub fn validate_document(_doc: &serde_json::Value) -> Result<(), ValidationError> {
    Ok(())
}

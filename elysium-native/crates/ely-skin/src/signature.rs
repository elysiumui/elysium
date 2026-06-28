//! Ed25519 signature verification for `signature.json`. Optional and
//! off-by-default; marketplace skins require signatures.

use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum SignatureError {
    #[error("malformed key")]
    Key,
    #[error("malformed signature")]
    Signature,
    #[error("signature verification failed")]
    Mismatch,
}

pub fn verify(
    pubkey_bytes: &[u8; 32],
    message: &[u8],
    sig_bytes: &[u8; 64],
) -> Result<(), SignatureError> {
    let key = VerifyingKey::from_bytes(pubkey_bytes).map_err(|_| SignatureError::Key)?;
    let sig = Signature::from_bytes(sig_bytes);
    key.verify(message, &sig)
        .map_err(|_| SignatureError::Mismatch)
}

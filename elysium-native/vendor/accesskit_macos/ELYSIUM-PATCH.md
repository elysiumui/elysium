# Elysium macOS text replacement backport

Source: AccessKit accesskit_macos 0.17.4, upstream commit
`c1bd2d610615a244fd9e8bba0a6c3aecbfe46821`, `platforms/macos`.
Copied from the published crate without modifying the global Cargo cache.
License files are from that exact upstream commit.

The upstream `setAccessibilityValue:` method is a no-op. This patch forwards
NSString replacements as Action::SetValue with ActionData::Value for enabled,
editable plain text controls. Other object types and read-only/disabled controls
are ignored. Existing text-range selector exposure is retained. Consumer 0.24
keeps generic action support private, so the adapter uses editable text roles;
the Elysium controller independently validates the current control and payload.

Remove this Cargo patch when upgrading to an upstream adapter with equivalent
behavior, after verifying native replacement, Cancel, validation and Apply.

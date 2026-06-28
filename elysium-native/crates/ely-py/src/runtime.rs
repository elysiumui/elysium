use std::sync::Once;

static INIT: Once = Once::new();

pub fn init_tracing() {
    INIT.call_once(|| {
        let _ = tracing_subscriber::fmt()
            .with_env_filter(
                tracing_subscriber::EnvFilter::try_from_env("ELYSIUM_LOG")
                    .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("warn,elysium=info")),
            )
            .try_init();
    });
}

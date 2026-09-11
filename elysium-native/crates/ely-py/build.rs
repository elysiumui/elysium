fn main() {
    cc::Build::new()
        .file("vendor/mikktspace/mikktspace.c")
        .file("src/tangents.c")
        .include("vendor/mikktspace")
        .compile("ely_mikktspace");
    for path in [
        "vendor/mikktspace/mikktspace.c",
        "vendor/mikktspace/mikktspace.h",
        "src/tangents.c",
    ] {
        println!("cargo:rerun-if-changed={path}");
    }
}

plugins {
    id("org.jetbrains.kotlin.jvm") version "1.9.24"
    id("org.jetbrains.intellij") version "1.17.4"
}

group   = "dev.elysium"
version = "0.1.0"

repositories { mavenCentral() }

dependencies {
    implementation("com.redhat.devtools.lsp4ij:lsp4ij:0.7.0")
}

intellij {
    version.set("2024.2")
    type.set("PC")    // PyCharm Community
    plugins.set(listOf("com.intellij.modules.python", "PythonCore"))
}

tasks {
    patchPluginXml {
        sinceBuild.set("242")
        untilBuild.set("251.*")
    }
    publishPlugin {
        token.set(System.getenv("JETBRAINS_MARKETPLACE_TOKEN"))
    }
    runIde { jvmArgs = listOf("-Xmx2048m") }
}

kotlin { jvmToolchain(17) }

package dev.elysium.pycharm.run

import com.intellij.execution.configurations.ConfigurationFactory
import com.intellij.execution.configurations.ConfigurationType
import com.intellij.execution.configurations.RunConfiguration
import com.intellij.execution.configurations.RunConfigurationBase
import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.configurations.CommandLineState
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.execution.Executor
import com.intellij.execution.process.ProcessHandler
import com.intellij.execution.process.ProcessHandlerFactory
import com.intellij.openapi.options.SettingsEditor
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.TextFieldWithBrowseButton
import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBLabel
import com.intellij.util.ui.FormBuilder
import org.jdom.Element
import javax.swing.Icon
import javax.swing.JComponent
import javax.swing.JPanel

class ElysiumAppConfigurationType : ConfigurationType {
    override fun getDisplayName() = "Elysium App"
    override fun getConfigurationTypeDescription() =
        "Run a Python Elysium UI app with hot-reload + inspector wired."
    override fun getIcon(): Icon? = null
    override fun getId(): String = "ElysiumAppConfiguration"
    override fun getConfigurationFactories(): Array<ConfigurationFactory> =
        arrayOf(ElysiumAppConfigurationFactory(this))
}

class ElysiumAppConfigurationFactory(type: ConfigurationType)
    : ConfigurationFactory(type) {
    override fun getId() = "ElysiumAppConfigurationFactory"
    override fun createTemplateConfiguration(project: Project): RunConfiguration =
        ElysiumAppRunConfiguration(project, this, "Elysium App")
}

class ElysiumAppRunConfiguration(
    project: Project, factory: ConfigurationFactory, name: String,
) : RunConfigurationBase<Any>(project, factory, name) {

    var entry:        String = "app/main.py"
    var skin:         String = ""
    var pythonBin:    String = "python"
    var hotReload:    Boolean = true
    var inspector:    Boolean = true
    var reduceMotion: Boolean = false

    override fun getConfigurationEditor(): SettingsEditor<out RunConfiguration> =
        ElysiumAppSettingsEditor()

    override fun writeExternal(element: Element) {
        super.writeExternal(element)
        element.setAttribute("entry",        entry)
        element.setAttribute("skin",         skin)
        element.setAttribute("python",       pythonBin)
        element.setAttribute("hotReload",    hotReload.toString())
        element.setAttribute("inspector",    inspector.toString())
        element.setAttribute("reduceMotion", reduceMotion.toString())
    }

    override fun readExternal(element: Element) {
        super.readExternal(element)
        entry        = element.getAttributeValue("entry")        ?: entry
        skin         = element.getAttributeValue("skin")         ?: skin
        pythonBin    = element.getAttributeValue("python")       ?: pythonBin
        hotReload    = element.getAttributeValue("hotReload")?.toBoolean() ?: hotReload
        inspector    = element.getAttributeValue("inspector")?.toBoolean() ?: inspector
        reduceMotion = element.getAttributeValue("reduceMotion")?.toBoolean() ?: reduceMotion
    }

    override fun getState(executor: Executor, env: ExecutionEnvironment) =
        object : CommandLineState(env) {
            override fun startProcess(): ProcessHandler {
                val cmd = GeneralCommandLine(pythonBin, entry)
                if (hotReload)    cmd.environment["ELYSIUM_HOT_RELOAD"]    = "1"
                if (inspector)    cmd.environment["ELYSIUM_INSPECTOR"]     = "1"
                if (reduceMotion) cmd.environment["ELYSIUM_REDUCE_MOTION"] = "1"
                if (skin.isNotEmpty()) cmd.environment["ELYSIUM_SKIN"]     = skin
                return ProcessHandlerFactory.getInstance()
                    .createColoredProcessHandler(cmd)
            }
        }
}

private class ElysiumAppSettingsEditor : SettingsEditor<ElysiumAppRunConfiguration>() {
    private val entryField = TextFieldWithBrowseButton().apply {
        addBrowseFolderListener("Entry Script", "Python file Elysium runs",
            null,
            FileChooserDescriptorFactory.createSingleFileDescriptor("py"))
    }
    private val skinField = TextFieldWithBrowseButton().apply {
        addBrowseFolderListener("Skin Directory", "Path to a .esk skin",
            null,
            FileChooserDescriptorFactory.createSingleFolderDescriptor())
    }
    private val pythonField    = TextFieldWithBrowseButton()
    private val hotReloadBox   = JBCheckBox("Enable hot-reload (ELYSIUM_HOT_RELOAD=1)", true)
    private val inspectorBox   = JBCheckBox("Stream stats to Inspector tool window (ELYSIUM_INSPECTOR=1)", true)
    private val reduceMotionBox = JBCheckBox("Force reduce-motion (ELYSIUM_REDUCE_MOTION=1)", false)

    override fun resetEditorFrom(s: ElysiumAppRunConfiguration) {
        entryField.text = s.entry
        skinField.text  = s.skin
        pythonField.text = s.pythonBin
        hotReloadBox.isSelected = s.hotReload
        inspectorBox.isSelected = s.inspector
        reduceMotionBox.isSelected = s.reduceMotion
    }
    override fun applyEditorTo(s: ElysiumAppRunConfiguration) {
        s.entry        = entryField.text
        s.skin         = skinField.text
        s.pythonBin    = pythonField.text.ifBlank { "python" }
        s.hotReload    = hotReloadBox.isSelected
        s.inspector    = inspectorBox.isSelected
        s.reduceMotion = reduceMotionBox.isSelected
    }
    override fun createEditor(): JComponent = FormBuilder.createFormBuilder()
        .addLabeledComponent(JBLabel("Entry script:"), entryField, 1, false)
        .addLabeledComponent(JBLabel("Skin (.esk):"),  skinField,  1, false)
        .addLabeledComponent(JBLabel("Python:"),       pythonField,1, false)
        .addComponent(hotReloadBox)
        .addComponent(inspectorBox)
        .addComponent(reduceMotionBox)
        .panel
}

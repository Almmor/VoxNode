package com.voxnode.remote

import android.app.AlertDialog
import android.content.ClipboardManager
import android.content.Context
import android.graphics.BitmapFactory
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.button.MaterialButton
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors

/**
 * VoxNode 手机遥控 App 主界面。
 *
 * 只依赖电脑端 VoxNode 的「遥控台」HTTP 接口，因此：
 *  - 不需要在手机上登录小米账号
 *  - 不经过任何第三方服务器，手机直连你自己的电脑
 *
 * 唤醒（WOL）是例外：电脑关机时服务并不可用，所以唤醒包由手机自己广播，
 * 相关设备列表保存在手机本地，与能否连上电脑无关。
 */
class MainActivity : AppCompatActivity() {

    private lateinit var setupPanel: View
    private lateinit var controlPanel: View
    private lateinit var editLink: EditText
    private lateinit var setupStatus: TextView
    private lateinit var txtHost: TextView
    private lateinit var txtCpu: TextView
    private lateinit var txtMem: TextView
    private lateinit var txtDisk: TextView
    private lateinit var barCpu: ProgressBar
    private lateinit var barMem: ProgressBar
    private lateinit var barDisk: ProgressBar
    private lateinit var boxApps: LinearLayout
    private lateinit var boxWol: LinearLayout
    private lateinit var txtAppsEmpty: TextView
    private lateinit var txtWolEmpty: TextView

    private var api: Api? = null
    private var refreshing = false
    private var configLoaded = false

    /** 电脑上报的网卡，用于「一键填入本机 MAC」。 */
    private var detectedNics: List<DetectedNic> = emptyList()

    /** 电脑主机名，用作自动添加的设备名称。 */
    private var serverHost = ""

    private val handler = Handler(Looper.getMainLooper())
    private val pool = Executors.newFixedThreadPool(4)

    private val refreshTask = object : Runnable {
        override fun run() {
            refreshStatus()
            handler.postDelayed(this, 4000)
        }
    }

    // 需要二次确认的动作 → 显示名资源
    private val dangerLabels = mapOf(
        "shutdown" to R.string.act_shutdown,
        "restart" to R.string.act_restart,
        "hibernate" to R.string.act_hibernate,
        "signout" to R.string.act_signout,
        "sleep" to R.string.act_sleep,
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        setupPanel = findViewById(R.id.setupPanel)
        controlPanel = findViewById(R.id.controlPanel)
        editLink = findViewById(R.id.editLink)
        setupStatus = findViewById(R.id.setupStatus)
        txtHost = findViewById(R.id.txtHost)
        txtCpu = findViewById(R.id.txtCpu)
        txtMem = findViewById(R.id.txtMem)
        txtDisk = findViewById(R.id.txtDisk)
        barCpu = findViewById(R.id.barCpu)
        barMem = findViewById(R.id.barMem)
        barDisk = findViewById(R.id.barDisk)
        boxApps = findViewById(R.id.boxApps)
        boxWol = findViewById(R.id.boxWol)
        txtAppsEmpty = findViewById(R.id.txtAppsEmpty)
        txtWolEmpty = findViewById(R.id.txtWolEmpty)

        findViewById<MaterialButton>(R.id.btnPaste).setOnClickListener { pasteFromClipboard() }
        findViewById<MaterialButton>(R.id.btnConnect).setOnClickListener { connect() }
        findViewById<MaterialButton>(R.id.btnSettings).setOnClickListener { showSetup(Prefs.baseUrl(this)) }
        findViewById<MaterialButton>(R.id.btnAddWol).setOnClickListener { showWolDialog(null) }

        wireAction(R.id.btnLock, "lock")
        wireAction(R.id.btnSleep, "sleep")
        wireAction(R.id.btnCancel, "cancel_shutdown")
        wireAction(R.id.btnHibernate, "hibernate")
        wireAction(R.id.btnSignout, "signout")
        wireAction(R.id.btnRestart, "restart", JSONObject().put("delay", 60))
        wireAction(R.id.btnShutdown, "shutdown", JSONObject().put("delay", 60))
        wireAction(R.id.btnScreenshot, "screenshot")
        wireAction(R.id.btnStatus, "report_status")
        findViewById<MaterialButton>(R.id.btnScreen).setOnClickListener { showScreenshot() }
        wireAction(R.id.btnVolDown, "volume", JSONObject().put("op", "减"))
        wireAction(R.id.btnMute, "volume", JSONObject().put("op", "静音"))
        wireAction(R.id.btnVolUp, "volume", JSONObject().put("op", "加"))
        wireAction(R.id.btnPrev, "media", JSONObject().put("op", "上一首"))
        wireAction(R.id.btnPlayPause, "media", JSONObject().put("op", "暂停"))
        wireAction(R.id.btnNext, "media", JSONObject().put("op", "下一首"))

        // 唤醒列表来自手机本地存储：电脑关机（还没连上）时同样要能看到并可用
        buildWolButtons()

        val saved = Prefs.baseUrl(this)
        val token = Prefs.token(this)
        if (saved.isNotEmpty() && token.isNotEmpty()) {
            api = Api(saved, token)
            showControl()
        } else {
            showSetup("")
        }
    }

    override fun onStart() {
        super.onStart()
        if (api != null) handler.post(refreshTask)
    }

    override fun onStop() {
        handler.removeCallbacks(refreshTask)
        super.onStop()
    }

    override fun onDestroy() {
        pool.shutdownNow()
        super.onDestroy()
    }

    // ---------------------------------------------------------------- 界面切换
    private fun showSetup(prefill: String) {
        setupPanel.visibility = View.VISIBLE
        controlPanel.visibility = View.GONE
        editLink.setText(prefill)
        setupStatus.text = ""
    }

    private fun showControl() {
        setupPanel.visibility = View.GONE
        controlPanel.visibility = View.VISIBLE
        configLoaded = false
        handler.post(refreshTask)
    }

    // ---------------------------------------------------------------- 连接
    private fun pasteFromClipboard() {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val text = cm.primaryClip?.getItemAt(0)?.coerceToText(this)?.toString().orEmpty()
        if (text.isBlank()) {
            setupStatus.text = getString(R.string.msg_no_clipboard)
        } else {
            editLink.setText(text.trim())
        }
    }

    private fun connect() {
        val parsed = Prefs.parseLink(editLink.text.toString())
        if (parsed == null) {
            setupStatus.text = if (editLink.text.isNullOrBlank())
                getString(R.string.msg_need_link) else getString(R.string.msg_link_invalid)
            return
        }
        val (base, token) = parsed
        if (token.isEmpty()) {
            setupStatus.text = getString(R.string.msg_link_invalid)
            return
        }
        setupStatus.text = getString(R.string.msg_connecting)
        val candidate = Api(base, token)
        pool.execute {
            try {
                candidate.status()
                runOnUiThread {
                    Prefs.save(this, base, token)
                    api = candidate
                    setupStatus.text = getString(R.string.msg_connected)
                    showControl()
                    loadClientConfig()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    setupStatus.text = getString(R.string.msg_connect_failed, e.message ?: e.javaClass.simpleName)
                }
            }
        }
    }

    // ---------------------------------------------------------------- 状态
    private fun refreshStatus() {
        val client = api ?: return
        if (refreshing) return
        refreshing = true
        pool.execute {
            try {
                val d = client.status()
                runOnUiThread {
                    refreshing = false
                    if (!d.optBoolean("ok", false)) return@runOnUiThread
                    txtHost.text = "${d.optString("hostname")} · ${d.optString("os")} · 已运行 ${d.optString("uptime")}"
                    bindStat(txtCpu, barCpu, d.optDouble("cpu_percent", 0.0))
                    bindStat(txtMem, barMem, d.optDouble("mem_percent", 0.0))
                    bindStat(txtDisk, barDisk, d.optDouble("disk_percent", 0.0))
                    if (!configLoaded) {
                        configLoaded = true
                        loadClientConfigOffThread(client)
                    }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    refreshing = false
                    txtHost.text = getString(R.string.msg_offline)
                }
            }
        }
    }

    private fun bindStat(label: TextView, bar: ProgressBar, percent: Double) {
        val value = Math.round(percent).coerceIn(0, 100).toInt()
        label.text = "$value%"
        bar.progress = value
    }

    // ---------------------------------------------------------------- 动态按钮
    private fun loadClientConfig() {
        val client = api ?: return
        pool.execute { loadClientConfigOffThread(client) }
    }

    private fun loadClientConfigOffThread(client: Api) {
        try {
            val cfg = client.clientConfig()
            val apps = toStringList(cfg.optJSONArray("apps"))
            val nics = Wol.parseNics(cfg.optJSONArray("macs"))
            val serverTargets = Wol.parseTargets(cfg.optJSONArray("wol_targets"))
            val host = cfg.optString("host", "")
            runOnUiThread {
                serverHost = host
                detectedNics = nics
                buildButtons(boxApps, txtAppsEmpty, apps) { name ->
                    doAction("open_app", JSONObject().put("app", name))
                }
                val added = importWolDevices(host, nics, serverTargets)
                buildWolButtons()
                if (added > 0) toast(getString(R.string.msg_wol_imported, added))
            }
        } catch (e: Exception) {
            // 动态列表加载失败不影响主要功能
        }
    }

    private fun toStringList(arr: JSONArray?): List<String> {
        if (arr == null) return emptyList()
        val out = ArrayList<String>(arr.length())
        for (i in 0 until arr.length()) {
            val v = arr.optString(i, "")
            if (v.isNotEmpty()) out.add(v)
        }
        return out
    }

    /** 把字符串列表铺成每行三个的按钮。 */
    private fun buildButtons(
        container: LinearLayout,
        emptyView: TextView,
        items: List<String>,
        onClick: (String) -> Unit,
    ) {
        container.removeAllViews()
        if (items.isEmpty()) {
            emptyView.visibility = View.VISIBLE
            return
        }
        emptyView.visibility = View.GONE
        var row: LinearLayout? = null
        items.forEachIndexed { index, name ->
            if (index % 3 == 0) {
                row = newRow()
                container.addView(row)
            }
            val button = layoutInflater
                .inflate(R.layout.item_button, row, false) as MaterialButton
            button.text = name
            button.isAllCaps = false
            val lp = button.layoutParams as LinearLayout.LayoutParams
            if (index % 3 != 0) lp.marginStart = dp(8)
            button.layoutParams = lp
            button.setOnClickListener { onClick(name) }
            row?.addView(button)
        }
    }

    private fun newRow(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = dp(8) }
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    // ---------------------------------------------------------------- 唤醒设备
    /** 手机本地保存的唤醒设备，每行两个（名字通常较长）。 */
    private fun buildWolButtons() {
        val targets = Prefs.wolTargets(this)
        boxWol.removeAllViews()
        if (targets.isEmpty()) {
            txtWolEmpty.visibility = View.VISIBLE
            return
        }
        txtWolEmpty.visibility = View.GONE
        var row: LinearLayout? = null
        targets.forEachIndexed { index, target ->
            if (index % 2 == 0) {
                row = newRow()
                boxWol.addView(row)
            }
            val button = layoutInflater
                .inflate(R.layout.item_button, row, false) as MaterialButton
            button.text = target.name
            button.isAllCaps = false
            val lp = button.layoutParams as LinearLayout.LayoutParams
            if (index % 2 != 0) lp.marginStart = dp(8)
            button.layoutParams = lp
            button.setOnClickListener { wake(target) }
            button.setOnLongClickListener { showWolActions(target); true }
            row?.addView(button)
        }
    }

    /** 手机自己广播魔术包 —— 电脑关机时唯一可行的路径。 */
    private fun wake(target: WolTarget) {
        toast(getString(R.string.msg_wol_sending))
        pool.execute {
            try {
                val sent = Wol.send(this, target)
                runOnUiThread {
                    toast(getString(R.string.msg_wol_sent, target.name, sent.joinToString(" · ")))
                }
            } catch (e: Exception) {
                val reason = e.message ?: e.javaClass.simpleName
                runOnUiThread { toast(getString(R.string.msg_wol_failed, reason)) }
            }
        }
    }

    private fun showWolActions(target: WolTarget) {
        val items = arrayOf(
            getString(R.string.wol_act_wake),
            getString(R.string.wol_act_edit),
            getString(R.string.wol_act_delete),
        )
        AlertDialog.Builder(this)
            .setTitle(getString(R.string.wol_actions_title, target.name))
            .setItems(items) { _, which ->
                when (which) {
                    0 -> wake(target)
                    1 -> showWolDialog(target)
                    else -> {
                        Prefs.removeWolTarget(this, target.mac)
                        buildWolButtons()
                        toast(getString(R.string.msg_wol_deleted, target.name))
                    }
                }
            }
            .setNegativeButton(R.string.dlg_cancel, null)
            .show()
    }

    /** 添加 / 编辑唤醒设备；existing 为 null 表示新增。 */
    private fun showWolDialog(existing: WolTarget?) {
        val view = layoutInflater.inflate(R.layout.dialog_add_wol, null)
        val nameInput = view.findViewById<EditText>(R.id.editWolName)
        val macInput = view.findViewById<EditText>(R.id.editWolMac)
        val bcastInput = view.findViewById<EditText>(R.id.editWolBcast)
        val portInput = view.findViewById<EditText>(R.id.editWolPort)
        val detectedLabel = view.findViewById<TextView>(R.id.wolDetectedLabel)
        val detectedBox = view.findViewById<LinearLayout>(R.id.boxWolDetected)

        nameInput.setText(existing?.name ?: "")
        macInput.setText(existing?.mac ?: "")
        bcastInput.setText(existing?.broadcast ?: "")
        portInput.setText((existing?.port ?: 9).toString())

        // 「一键填入电脑网卡」快捷按钮
        if (detectedNics.isEmpty()) {
            detectedLabel.text = getString(R.string.wol_no_detected)
        } else {
            detectedNics.forEach { nic ->
                val chip = layoutInflater
                    .inflate(R.layout.item_button, detectedBox, false) as MaterialButton
                chip.text = "${nic.name} · ${nic.mac}"
                chip.isAllCaps = false
                chip.textSize = 12f
                val lp = chip.layoutParams as LinearLayout.LayoutParams
                lp.width = LinearLayout.LayoutParams.MATCH_PARENT
                lp.weight = 0f
                if (detectedBox.childCount > 0) lp.topMargin = dp(8)
                chip.layoutParams = lp
                chip.setOnClickListener {
                    val label = serverHost.ifBlank {
                        nic.name.ifBlank { getString(R.string.wol_default_pc_name) }
                    }
                    nameInput.setText(label)
                    macInput.setText(nic.mac)
                    if (nic.broadcast.isNotBlank()) bcastInput.setText(nic.broadcast)
                }
                detectedBox.addView(chip)
            }
        }

        val dialog = AlertDialog.Builder(this)
            .setTitle(
                if (existing == null) R.string.dlg_wol_add_title else R.string.dlg_wol_edit_title
            )
            .setView(view)
            .setPositiveButton(R.string.dlg_save, null)
            .setNegativeButton(R.string.dlg_cancel, null)
            .create()

        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val name = nameInput.text.toString().trim()
                val mac = macInput.text.toString().trim()
                if (name.isEmpty()) {
                    toast(getString(R.string.msg_wol_need_name))
                    return@setOnClickListener
                }
                if (mac.isEmpty()) {
                    toast(getString(R.string.msg_wol_need_mac))
                    return@setOnClickListener
                }
                if (!Wol.isValidMac(mac)) {
                    toast(getString(R.string.msg_wol_bad_mac))
                    return@setOnClickListener
                }
                val port = portInput.text.toString().trim().toIntOrNull()?.takeIf { it in 1..65535 } ?: 9
                val broadcast = bcastInput.text.toString().trim().ifBlank { "255.255.255.255" }
                val target = WolTarget(
                    name = name,
                    mac = mac,
                    broadcast = broadcast,
                    port = port,
                )

                // 编辑时改了 MAC，先把旧记录删掉，避免留下一条死设备
                if (existing != null && !sameMac(existing.mac, target.mac)) {
                    Prefs.removeWolTarget(this, existing.mac)
                }
                Prefs.upsertWolTarget(this, target)
                buildWolButtons()
                toast(getString(R.string.msg_wol_saved, target.name))
                dialog.dismiss()
            }
        }
        dialog.show()
    }

    private fun sameMac(a: String, b: String): Boolean {
        val left = runCatching { Wol.normalizeMac(a) }.getOrDefault(a)
        val right = runCatching { Wol.normalizeMac(b) }.getOrDefault(b)
        return left.equals(right, ignoreCase = true)
    }

    /**
     * 把电脑上报的设备并入手机本地列表：
     *  - 电脑自己的网卡（用主机名命名）—— 这就是「绑定这台电脑」
     *  - 服务器上配置的其他唤醒目标
     *
     * 只在从未见过该 MAC 时添加，用户删掉后不会自动复活。
     * 返回新增数量。
     */
    private fun importWolDevices(
        host: String,
        nics: List<DetectedNic>,
        serverTargets: List<WolTarget>,
    ): Int {
        val existing = Prefs.wolTargets(this)
        val known = existing.mapNotNull { macKey(it.mac) }.toMutableSet()
        val imported = Prefs.importedMacs(this).toMutableSet()
        val added = ArrayList<WolTarget>()

        fun consider(target: WolTarget, fallbackName: String) {
            val key = macKey(target.mac) ?: return
            if (key in known || key in imported) return
            val name = target.name.ifBlank { fallbackName }
            added.add(target.copy(name = name))
            known.add(key)
            imported.add(key)
        }

        val pcName = host.ifBlank { getString(R.string.wol_default_pc_name) }
        Wol.pickPrimaryNic(nics)?.let { nic ->
            consider(
                WolTarget(
                    name = pcName,
                    mac = nic.mac,
                    broadcast = nic.broadcast.ifBlank { "255.255.255.255" },
                    port = 9,
                ),
                pcName,
            )
        }
        serverTargets.forEach { consider(it, it.name) }

        if (added.isEmpty()) return 0
        Prefs.saveWolTargets(this, existing + added)
        Prefs.saveImportedMacs(this, imported)
        return added.size
    }

    private fun macKey(mac: String): String? =
        runCatching { Wol.normalizeMac(mac) }.getOrNull()

    // ---------------------------------------------------------------- 动作
    private fun wireAction(viewId: Int, action: String, params: JSONObject? = null) {
        findViewById<MaterialButton>(viewId).setOnClickListener { doAction(action, params) }
    }

    private fun doAction(action: String, params: JSONObject? = null) {
        val labelRes = dangerLabels[action]
        if (labelRes != null) {
            val label = getString(labelRes)
            AlertDialog.Builder(this)
                .setTitle(R.string.dlg_confirm_title)
                .setMessage(getString(R.string.dlg_confirm_msg, label))
                .setPositiveButton(R.string.dlg_ok) { _, _ -> sendAction(action, params) }
                .setNegativeButton(R.string.dlg_cancel, null)
                .show()
        } else {
            sendAction(action, params)
        }
    }

    private fun sendAction(action: String, params: JSONObject?) {
        val client = api ?: return
        pool.execute {
            try {
                val res = client.action(action, params ?: JSONObject())
                val text = if (res.optBoolean("ok", false)) {
                    res.optString("reply").ifEmpty { getString(R.string.msg_connected) }
                } else {
                    getString(R.string.msg_connect_failed, res.optString("reply", "unknown"))
                }
                runOnUiThread {
                    if (action == "shutdown" || action == "restart") refreshStatus()
                    toast(text)
                }
            } catch (e: Exception) {
                runOnUiThread { toast(getString(R.string.msg_connect_failed, e.message ?: "error")) }
            }
        }
    }

    // ---------------------------------------------------------------- 截图
    private fun showScreenshot() {
        val client = api ?: return
        pool.execute {
            try {
                val bytes = client.screenshot()
                val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                if (bitmap == null) throw Api.ApiException("图片解码失败")
                runOnUiThread {
                    val image = ImageView(this).apply {
                        setImageBitmap(bitmap)
                        adjustViewBounds = true
                    }
                    AlertDialog.Builder(this)
                        .setTitle(R.string.act_view_screen)
                        .setView(image)
                        .setPositiveButton(R.string.dlg_close, null)
                        .show()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    toast(getString(R.string.msg_screenshot_failed, e.message ?: "error"))
                }
            }
        }
    }

    private fun toast(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }
}

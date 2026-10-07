package com.voxnode.remote

import android.content.Context
import android.net.wifi.WifiManager
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

/**
 * 一个「由手机直接唤醒」的目标设备。
 *
 * 关键点：唤醒包完全由手机发出，不经过电脑端服务 ——
 * 因为电脑一旦关机，VoxNode 的服务也就停了，没法替手机转发。
 */
data class WolTarget(
    val name: String,
    val mac: String,
    val broadcast: String = "255.255.255.255",
    val port: Int = 9,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("name", name)
        .put("mac", mac)
        .put("broadcast", broadcast)
        .put("port", port)

    companion object {
        fun fromJson(o: JSONObject): WolTarget = WolTarget(
            name = o.optString("name", ""),
            mac = o.optString("mac", ""),
            broadcast = o.optString("broadcast", "").ifBlank { "255.255.255.255" },
            port = o.optInt("port", 9).let { if (it in 1..65535) it else 9 },
        )
    }
}

/** 电脑端上报的网卡信息，用于「一键填入本机 MAC」。 */
data class DetectedNic(
    val name: String,
    val mac: String,
    val ipv4: String,
    val broadcast: String,
)

/**
 * Wake-on-LAN：在手机侧构造并广播魔术包。
 *
 * 魔术包格式：6 字节 0xFF + 目标 MAC 重复 16 次，共 102 字节。
 * 依次发往子网广播地址与 255.255.255.255，命中率最高。
 */
object Wol {

    private val MAC_RE = Regex("^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$")
    private val IPV4_RE = Regex("^\\d{1,3}(\\.\\d{1,3}){3}$")

    /** 校验并统一成 AA:BB:CC:DD:EE:FF 形式；非法时抛 IllegalArgumentException。 */
    fun normalizeMac(mac: String): String {
        val m = mac.trim().replace(" ", "").replace("-", ":").uppercase()
        require(MAC_RE.matches(m)) { "MAC 地址格式不对，应形如 AA:BB:CC:DD:EE:FF" }
        return m
    }

    fun isValidMac(mac: String): Boolean =
        runCatching { normalizeMac(mac) }.isSuccess

    /** 构造 102 字节魔术包。 */
    fun magicPacket(mac: String): ByteArray {
        val hex = normalizeMac(mac).replace(":", "")
        val macBytes = ByteArray(6) { i -> hex.substring(i * 2, i * 2 + 2).toInt(16).toByte() }
        val packet = ByteArray(6 + 16 * 6)
        for (i in 0 until 6) packet[i] = 0xFF.toByte()
        for (round in 0 until 16) {
            System.arraycopy(macBytes, 0, packet, 6 + round * 6, 6)
        }
        return packet
    }

    /**
     * 发送唤醒包。依次尝试子网广播地址、全网广播地址，
     * 返回实际发送成功的地址列表（空表示全部失败）。
     */
    fun send(ctx: Context, target: WolTarget): List<String> {
        val packet = magicPacket(target.mac)
        val port = if (target.port in 1..65535) target.port else 9

        // 端口对 WOL 其实不敏感（网卡只看包内容），多打一个 9 提升兼容性
        val ports = if (port == 9) listOf(9) else listOf(port, 9)

        val candidates = LinkedHashSet<String>()
        val subnet = target.broadcast.trim()
        if (subnet.isNotEmpty() && subnet != "0.0.0.0" && IPV4_RE.matches(subnet)) {
            candidates.add(subnet)
        }
        candidates.add("255.255.255.255")

        val lock = acquireMulticastLock(ctx)
        try {
            val sent = ArrayList<String>()
            DatagramSocket().use { socket ->
                socket.broadcast = true
                socket.soTimeout = 2000
                for (address in candidates) {
                    val reachable = runCatching { InetAddress.getByName(address) }.getOrNull()
                        ?: continue
                    var ok = false
                    for (p in ports) {
                        val done = runCatching {
                            socket.send(DatagramPacket(packet, packet.size, reachable, p))
                        }.isSuccess
                        ok = ok || done
                    }
                    if (ok) sent.add(address)
                }
            }
            if (sent.isEmpty()) {
                throw IllegalStateException("没有可用的广播地址，请检查手机是否已连上 Wi-Fi")
            }
            return sent
        } finally {
            releaseLock(lock)
        }
    }

    /** 部分机型在省电策略下会拦住广播，短暂持锁更稳。 */
    private fun acquireMulticastLock(ctx: Context): WifiManager.MulticastLock? = runCatching {
        val wm = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        wm.createMulticastLock("voxnode-wol").apply {
            setReferenceCounted(false)
            acquire()
        }
    }.getOrNull()

    private fun releaseLock(lock: WifiManager.MulticastLock?) {
        runCatching { lock?.takeIf { it.isHeld }?.release() }
    }

    /** 解析电脑端 /api/config 里的 wol_targets。 */
    fun parseTargets(array: org.json.JSONArray?): List<WolTarget> {
        if (array == null) return emptyList()
        val out = ArrayList<WolTarget>(array.length())
        for (i in 0 until array.length()) {
            val o = array.optJSONObject(i) ?: continue
            val t = WolTarget.fromJson(o)
            if (isValidMac(t.mac)) out.add(t)
        }
        return out
    }

    /** 解析电脑端 /api/config 里的 macs（本机网卡）。 */
    fun parseNics(array: org.json.JSONArray?): List<DetectedNic> {
        if (array == null) return emptyList()
        val out = ArrayList<DetectedNic>(array.length())
        for (i in 0 until array.length()) {
            val o = array.optJSONObject(i) ?: continue
            val mac = o.optString("mac", "")
            if (!isValidMac(mac)) continue
            out.add(
                DetectedNic(
                    name = o.optString("name", ""),
                    mac = mac,
                    ipv4 = o.optString("ipv4", ""),
                    broadcast = o.optString("broadcast", ""),
                )
            )
        }
        return out
    }

    /**
     * 从电脑上报的网卡里挑一张「最像主网卡」的。
     * 排除虚拟网卡 / 蓝牙 / 虚拟机网卡，优先无线与以太网。
     */
    fun pickPrimaryNic(nics: List<DetectedNic>): DetectedNic? {
        val skip = listOf(
            "virtual", "vmware", "hyper-v", "vethernet", "virtualbox",
            "bluetooth", "蓝牙", "loopback", "虚拟机", "tap", "tun", "zerotier", "tailscale",
        )
        val prefer = listOf("wi-fi", "wifi", "wlan", "wireless", "无线", "以太", "ethernet")
        return nics
            .filter { it.mac.isNotEmpty() && !it.ipv4.startsWith("169.254.") }
            .filterNot { nic -> skip.any { nic.name.lowercase().contains(it) } }
            .maxByOrNull { nic ->
                (if (nic.broadcast.isNotBlank()) 2 else 0) +
                    (if (prefer.any { nic.name.lowercase().contains(it) }) 1 else 0)
            }
    }
}

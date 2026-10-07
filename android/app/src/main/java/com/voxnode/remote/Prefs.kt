package com.voxnode.remote

import android.content.Context
import android.content.SharedPreferences
import android.net.Uri
import org.json.JSONArray

/** 保存遥控台的地址、访问令牌，以及本机维护的唤醒设备列表。 */
object Prefs {
    private const val FILE = "voxnode"
    private const val KEY_BASE = "base_url"
    private const val KEY_TOKEN = "token"
    private const val KEY_WOL = "wol_targets"
    /** 曾经自动添加过的 MAC：用户删掉后不再自动加回来。 */
    private const val KEY_WOL_IMPORTED = "wol_imported"

    private fun store(ctx: Context): SharedPreferences =
        ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    // ---------------------------------------------------------------- 服务器
    fun save(ctx: Context, baseUrl: String, token: String) {
        store(ctx).edit()
            .putString(KEY_BASE, baseUrl)
            .putString(KEY_TOKEN, token)
            .apply()
    }

    fun baseUrl(ctx: Context): String = store(ctx).getString(KEY_BASE, "") ?: ""

    fun token(ctx: Context): String = store(ctx).getString(KEY_TOKEN, "") ?: ""

    /** 只清除服务器信息，保留唤醒设备（唤醒能力与能否连上电脑无关）。 */
    fun clearServer(ctx: Context) {
        store(ctx).edit().remove(KEY_BASE).remove(KEY_TOKEN).apply()
    }

    fun clear(ctx: Context) {
        store(ctx).edit().clear().apply()
    }

    // ---------------------------------------------------------------- 唤醒设备
    fun wolTargets(ctx: Context): MutableList<WolTarget> {
        val raw = store(ctx).getString(KEY_WOL, "") ?: ""
        if (raw.isBlank()) return mutableListOf()
        return try {
            val arr = JSONArray(raw)
            val out = ArrayList<WolTarget>(arr.length())
            for (i in 0 until arr.length()) {
                val o = arr.optJSONObject(i) ?: continue
                val t = WolTarget.fromJson(o)
                if (t.name.isNotBlank() && t.mac.isNotBlank()) out.add(t)
            }
            out
        } catch (e: Exception) {
            mutableListOf()
        }
    }

    fun saveWolTargets(ctx: Context, list: List<WolTarget>) {
        val arr = JSONArray()
        list.forEach { arr.put(it.toJson()) }
        store(ctx).edit().putString(KEY_WOL, arr.toString()).apply()
    }

    /** 新增或按 MAC 覆盖同名记录。 */
    fun upsertWolTarget(ctx: Context, target: WolTarget) {
        val list = wolTargets(ctx)
        val key = runCatching { Wol.normalizeMac(target.mac) }.getOrDefault(target.mac.uppercase())
        val index = list.indexOfFirst {
            runCatching { Wol.normalizeMac(it.mac) }.getOrDefault(it.mac.uppercase()) == key
        }
        if (index >= 0) list[index] = target else list.add(target)
        saveWolTargets(ctx, list)
    }

    fun removeWolTarget(ctx: Context, mac: String) {
        val key = runCatching { Wol.normalizeMac(mac) }.getOrDefault(mac.uppercase())
        val list = wolTargets(ctx).filterNot {
            runCatching { Wol.normalizeMac(it.mac) }.getOrDefault(it.mac.uppercase()) == key
        }
        saveWolTargets(ctx, list)
    }

    fun importedMacs(ctx: Context): Set<String> {
        val raw = store(ctx).getString(KEY_WOL_IMPORTED, "") ?: ""
        if (raw.isBlank()) return emptySet()
        return raw.split(',').map { it.trim().uppercase() }.filter { it.isNotEmpty() }.toSet()
    }

    fun saveImportedMacs(ctx: Context, macs: Set<String>) {
        store(ctx).edit().putString(KEY_WOL_IMPORTED, macs.joinToString(",")).apply()
    }

    // ---------------------------------------------------------------- 链接解析
    /**
     * 解析用户在电脑上复制过来的完整链接，例如：
     *   http://192.168.1.5:8765/?t=AbC123
     * 也接受不带 token 的 http://192.168.1.5:8765
     */
    fun parseLink(link: String): Pair<String, String>? {
        val text = link.trim()
        if (text.isEmpty()) return null
        val withScheme = if (text.startsWith("http://") || text.startsWith("https://")) {
            text
        } else {
            "http://$text"
        }
        return try {
            val uri = Uri.parse(withScheme)
            val host = uri.host ?: return null
            val port = if (uri.port > 0) uri.port else 8765
            val token = uri.getQueryParameter("t") ?: ""
            "http://$host:$port" to token
        } catch (e: Exception) {
            null
        }
    }
}

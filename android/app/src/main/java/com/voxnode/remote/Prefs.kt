package com.voxnode.remote

import android.content.Context
import android.net.Uri

/** 保存遥控台的地址与访问令牌。 */
object Prefs {
    private const val FILE = "voxnode"
    private const val KEY_BASE = "base_url"
    private const val KEY_TOKEN = "token"

    fun save(ctx: Context, baseUrl: String, token: String) {
        ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit()
            .putString(KEY_BASE, baseUrl)
            .putString(KEY_TOKEN, token)
            .apply()
    }

    fun baseUrl(ctx: Context): String =
        ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE).getString(KEY_BASE, "") ?: ""

    fun token(ctx: Context): String =
        ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE).getString(KEY_TOKEN, "") ?: ""

    fun clear(ctx: Context) {
        ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit().clear().apply()
    }

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

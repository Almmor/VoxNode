package com.voxnode.remote

import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * 遥控台 HTTP 客户端。
 *
 * 只用 HttpURLConnection + org.json，不引入 OkHttp/Retrofit，
 * 这样依赖最少、构建最稳、APK 最小。
 */
class Api(private val baseUrl: String, private val token: String) {

    class ApiException(message: String) : Exception(message)

    private fun open(path: String): HttpURLConnection {
        val sep = if (path.contains("?")) "&" else "?"
        val url = URL("$baseUrl$path${sep}t=${URLEncoder.encode(token, "UTF-8")}")
        val conn = url.openConnection() as HttpURLConnection
        conn.connectTimeout = 6000
        conn.readTimeout = 10000
        conn.requestMethod = "GET"
        return conn
    }

    private fun readText(conn: HttpURLConnection): String {
        val stream = if (conn.responseCode in 200..299) conn.inputStream else conn.errorStream
        val body = stream?.let {
            BufferedReader(InputStreamReader(it, "UTF-8")).use { r -> r.readText() }
        } ?: ""
        if (conn.responseCode !in 200..299) {
            val message = try {
                JSONObject(body).optString("error", "HTTP ${conn.responseCode}")
            } catch (e: Exception) {
                "HTTP ${conn.responseCode}"
            }
            throw ApiException(message)
        }
        return body
    }

    /** 读取系统状态（CPU / 内存 / 磁盘 / 运行时长）。 */
    fun status(): JSONObject {
        val conn = open("/api/status")
        try {
            return JSONObject(readText(conn))
        } finally {
            conn.disconnect()
        }
    }

    /** 可点项：已配置的应用与唤醒目标。 */
    fun clientConfig(): JSONObject {
        val conn = open("/api/config")
        try {
            return JSONObject(readText(conn))
        } finally {
            conn.disconnect()
        }
    }

    /** 执行动作，例如 action("lock") / action("shutdown", {"delay":60})。 */
    fun action(action: String, params: JSONObject = JSONObject()): JSONObject {
        val url = URL("$baseUrl/api/action?t=${URLEncoder.encode(token, "UTF-8")}")
        val conn = url.openConnection() as HttpURLConnection
        conn.connectTimeout = 6000
        conn.readTimeout = 10000
        conn.requestMethod = "POST"
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        val body = JSONObject().put("action", action).put("params", params).toString()
        try {
            conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            return JSONObject(readText(conn))
        } finally {
            conn.disconnect()
        }
    }

    /** 取最近一张截图。 */
    fun screenshot(): ByteArray {
        val conn = open("/api/screenshot")
        try {
            if (conn.responseCode !in 200..299) {
                throw ApiException("暂时没有截图，请先点「截屏」")
            }
            return conn.inputStream.use { it.readBytes() }
        } finally {
            conn.disconnect()
        }
    }
}

package com.osynskyi.drumpractice.audio

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.sin
import kotlin.random.Random

/**
 * Барабанные звуки, синтезированные кодом при запуске.
 * Никаких чужих сэмплов — значит, нет проблем с авторскими правами при публикации.
 */
class DrumKit(private val sampleRate: Int) {

    /** Звуки в порядке дорожек из [com.osynskyi.drumpractice.model.Track]. */
    val tracks: Array<FloatArray> = arrayOf(
        kick(), snare(), hat(), openHat(), tom(200.0, 0.30), tom(120.0, 0.42), rim(), ride(),
    )

    /** Относительная громкость каждой дорожки, чтобы хэт не заглушал бочку. */
    val gains: FloatArray = floatArrayOf(1.0f, 0.9f, 0.5f, 0.5f, 0.9f, 0.9f, 0.7f, 0.5f)

    val click: FloatArray = clickSound(1000.0)
    val clickAccent: FloatArray = clickSound(1600.0)

    private fun make(seconds: Double, f: (t: Double) -> Double): FloatArray {
        val n = (seconds * sampleRate).toInt()
        val out = FloatArray(n)
        for (i in 0 until n) out[i] = f(i.toDouble() / sampleRate).toFloat()

        // Короткое затухание в конце, чтобы не было щелчка.
        val fade = minOf(64, n)
        for (i in 0 until fade) out[n - 1 - i] *= i.toFloat() / fade

        var peak = 0f
        for (v in out) peak = maxOf(peak, abs(v))
        if (peak > 0f) {
            val k = 0.95f / peak
            for (i in out.indices) out[i] *= k
        }
        return out
    }

    private fun kick(): FloatArray {
        val rnd = Random(1)
        var phase = 0.0
        return make(0.45) { t ->
            val freq = 45.0 + 130.0 * exp(-t / 0.025)
            phase += 2 * PI * freq / sampleRate
            sin(phase) * exp(-t / 0.11) + 0.15 * (rnd.nextDouble() * 2 - 1) * exp(-t / 0.003)
        }
    }

    private fun snare(): FloatArray {
        val rnd = Random(2)
        var prev = 0.0
        return make(0.30) { t ->
            val n = rnd.nextDouble() * 2 - 1
            val noise = n - 0.6 * prev
            prev = n
            0.8 * noise * exp(-t / 0.06) +
                0.6 * sin(2 * PI * 185.0 * t) * exp(-t / 0.05) +
                0.3 * sin(2 * PI * 330.0 * t) * exp(-t / 0.03)
        }
    }

    private fun hatLike(seconds: Double, decay: Double, seed: Int): FloatArray {
        val rnd = Random(seed)
        var prev = 0.0
        return make(seconds) { t ->
            val n = rnd.nextDouble() * 2 - 1
            val hp = n - prev
            prev = n
            val metal = sin(2 * PI * 3500.0 * t) + sin(2 * PI * 5200.0 * t) + sin(2 * PI * 7300.0 * t)
            (hp + 0.25 * metal) * exp(-t / decay)
        }
    }

    private fun hat(): FloatArray = hatLike(0.12, 0.022, 3)

    private fun openHat(): FloatArray = hatLike(0.60, 0.12, 4)

    private fun tom(baseFreq: Double, decay: Double): FloatArray {
        var phase = 0.0
        return make(decay * 2) { t ->
            val freq = baseFreq * (1.0 + 0.6 * exp(-t / 0.04))
            phase += 2 * PI * freq / sampleRate
            sin(phase) * exp(-t / decay)
        }
    }

    private fun rim(): FloatArray {
        val rnd = Random(5)
        return make(0.08) { t ->
            (sin(2 * PI * 1750.0 * t) + 0.6 * sin(2 * PI * 480.0 * t)) * exp(-t / 0.012) +
                0.3 * (rnd.nextDouble() * 2 - 1) * exp(-t / 0.006)
        }
    }

    private fun ride(): FloatArray {
        val rnd = Random(6)
        var prev = 0.0
        return make(0.9) { t ->
            val n = rnd.nextDouble() * 2 - 1
            val hp = n - prev
            prev = n
            val bell = sin(2 * PI * 3150.0 * t) + sin(2 * PI * 4430.0 * t) +
                sin(2 * PI * 5870.0 * t) + sin(2 * PI * 7320.0 * t)
            0.3 * hp * exp(-t / 0.25) + 0.4 * bell * exp(-t / 0.3)
        }
    }

    private fun clickSound(freq: Double): FloatArray =
        make(0.025) { t -> sin(2 * PI * freq * t) * exp(-t / 0.006) }
}

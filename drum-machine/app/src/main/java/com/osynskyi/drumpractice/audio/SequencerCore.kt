package com.osynskyi.drumpractice.audio

import com.osynskyi.drumpractice.model.Track
import kotlin.math.min
import kotlin.math.tanh

/**
 * Секвенсор и микшер без привязки к Android.
 *
 * Время считается в сэмплах, а не в миллисекундах: каждый удар попадает ровно в нужный
 * кадр звукового буфера. Поэтому ритм не «плавает», как при таймерах.
 */
class SequencerCore(private val kit: DrumKit, private val sampleRate: Int) {

    class Pattern(val steps: Int, val stepsPerBeat: Int, val grid: Array<IntArray>)

    @Volatile var pattern = Pattern(16, 4, Array(Track.COUNT) { IntArray(16) })
    @Volatile var bpm = 100
    @Volatile var metronome = false
    @Volatile var countIn = false
    @Volatile var mutedMask = 0
    @Volatile var rampEnabled = false
    @Volatile var rampStepBpm = 5
    @Volatile var rampEveryBars = 4
    @Volatile var rampMaxBpm = 220

    /** Номер клетки, которая только что зазвучала; -1 во время вступительного счёта. */
    var onStep: (Int) -> Unit = {}
    var onBpmChanged: (Int) -> Unit = {}

    private val voiceSample = arrayOfNulls<FloatArray>(MAX_VOICES)
    private val voicePos = IntArray(MAX_VOICES)
    private val voiceGain = FloatArray(MAX_VOICES)
    private val voiceGroup = IntArray(MAX_VOICES)
    private var nextVoice = 0

    private var frameCounter = 0L
    private var nextStepFrame = 0.0
    private var stepPos = 0
    private var countInLeft = 0
    private var countInTotal = 0
    private var countInSpb = 4
    private var barsSinceRamp = 0

    fun reset() {
        for (i in voiceSample.indices) voiceSample[i] = null
        frameCounter = 0
        nextStepFrame = 0.0
        stepPos = 0
        barsSinceRamp = 0
        val pat = pattern
        countInTotal = pat.steps
        countInSpb = pat.stepsPerBeat
        countInLeft = if (countIn) pat.steps else 0
    }

    fun activeVoices(): Int = voiceSample.count { it != null }

    /** Заполняет [out] моно-звуком. */
    fun render(out: FloatArray, frames: Int) {
        for (i in 0 until frames) {
            while (frameCounter >= nextStepFrame) advanceStep()

            var acc = 0f
            for (v in 0 until MAX_VOICES) {
                val s = voiceSample[v] ?: continue
                val p = voicePos[v]
                acc += s[p] * voiceGain[v]
                if (p + 1 >= s.size) voiceSample[v] = null else voicePos[v] = p + 1
            }
            out[i] = tanh(acc * 0.9f)
            frameCounter++
        }
    }

    private fun advanceStep() {
        val pat = pattern
        if (countInLeft > 0) {
            val idx = countInTotal - countInLeft
            if (idx % countInSpb == 0) {
                trigger(if (idx == 0) kit.clickAccent else kit.click, CLICK_GAIN, 0)
            }
            countInLeft--
            onStep(-1)
        } else {
            if (stepPos >= pat.steps) stepPos = 0
            val s = stepPos
            val muted = mutedMask
            for (t in 0 until Track.COUNT) {
                if (((muted shr t) and 1) != 0) continue
                val row = pat.grid[t]
                val level = if (s < row.size) row[s] else 0
                if (level > 0) {
                    trigger(kit.tracks[t], kit.gains[t] * VELOCITY[level], Track.chokeGroup[t])
                }
            }
            if (metronome && s % pat.stepsPerBeat == 0) {
                trigger(if (s == 0) kit.clickAccent else kit.click, CLICK_GAIN, 0)
            }
            onStep(s)
            stepPos++
            if (stepPos >= pat.steps) {
                stepPos = 0
                onBarCompleted()
            }
        }
        nextStepFrame += sampleRate * 60.0 / (bpm.coerceAtLeast(20) * pat.stepsPerBeat)
    }

    private fun onBarCompleted() {
        if (!rampEnabled) return
        barsSinceRamp++
        if (barsSinceRamp >= rampEveryBars) {
            barsSinceRamp = 0
            val next = min(bpm + rampStepBpm, rampMaxBpm)
            if (next != bpm) {
                bpm = next
                onBpmChanged(next)
            }
        }
    }

    private fun trigger(sample: FloatArray, gain: Float, group: Int) {
        if (group != 0) {
            for (v in 0 until MAX_VOICES) {
                if (voiceSample[v] != null && voiceGroup[v] == group) voiceSample[v] = null
            }
        }
        var slot = -1
        for (v in 0 until MAX_VOICES) {
            if (voiceSample[v] == null) { slot = v; break }
        }
        if (slot < 0) {
            slot = nextVoice
            nextVoice = (nextVoice + 1) % MAX_VOICES
        }
        voiceSample[slot] = sample
        voicePos[slot] = 0
        voiceGain[slot] = gain
        voiceGroup[slot] = group
    }

    companion object {
        const val MAX_VOICES = 32
        private const val CLICK_GAIN = 0.5f

        /** Громкость по уровню клетки (индекс 0 не используется). */
        private val VELOCITY = floatArrayOf(0f, 0.35f, 0.7f, 1.0f)
    }
}

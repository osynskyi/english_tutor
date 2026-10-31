package com.osynskyi.drumpractice.model

/** Дорожки барабанной установки. */
object Track {
    const val KICK = 0
    const val SNARE = 1
    const val HAT = 2
    const val OPEN_HAT = 3
    const val TOM_HI = 4
    const val TOM_LO = 5
    const val RIM = 6
    const val RIDE = 7
    const val COUNT = 8

    val names = listOf("Бочка", "Малый", "Хэт", "Откр. хэт", "Том 1", "Том 2", "Рим", "Райд")

    /** Закрытый и открытый хэт глушат друг друга, как на настоящей установке. */
    val chokeGroup = intArrayOf(0, 0, 1, 1, 0, 0, 0, 0)
}

/** Уровни громкости клетки: 0 — пусто, 1 — тихо, 2 — обычно, 3 — громко. */
object Level {
    const val OFF = 0
    const val GHOST = 1
    const val NORMAL = 2
    const val ACCENT = 3

    /** Что происходит при нажатии на клетку: пусто → обычно → громко → тихо → пусто. */
    fun next(level: Int): Int = when (level) {
        OFF -> NORMAL
        NORMAL -> ACCENT
        ACCENT -> GHOST
        else -> OFF
    }
}

/**
 * Готовый ритм.
 *
 * [steps] — число клеток в такте, [stepsPerBeat] — сколько клеток приходится на одну долю
 * (4 — шестнадцатые, 3 — триоли).
 * Строки: '.' пусто, 'g' тихо, 'x' обычно, 'X' громко.
 */
data class Preset(
    val name: String,
    val genre: String,
    val bpm: Int,
    val steps: Int,
    val stepsPerBeat: Int,
    val rows: Map<Int, String>,
) {
    fun toGrid(): List<List<Int>> = List(Track.COUNT) { t -> parseRow(rows[t], steps) }
}

fun parseRow(row: String?, steps: Int): List<Int> = List(steps) { i ->
    when (row?.getOrNull(i)) {
        'g' -> Level.GHOST
        'x' -> Level.NORMAL
        'X' -> Level.ACCENT
        else -> Level.OFF
    }
}

private fun preset(
    name: String,
    genre: String,
    bpm: Int,
    steps: Int = 16,
    spb: Int = 4,
    kick: String = "",
    snare: String = "",
    hat: String = "",
    open: String = "",
    tom1: String = "",
    tom2: String = "",
    rim: String = "",
    ride: String = "",
): Preset {
    val rows = mapOf(
        Track.KICK to kick,
        Track.SNARE to snare,
        Track.HAT to hat,
        Track.OPEN_HAT to open,
        Track.TOM_HI to tom1,
        Track.TOM_LO to tom2,
        Track.RIM to rim,
        Track.RIDE to ride,
    ).filterValues { it.isNotEmpty() }
    return Preset(name, genre, bpm, steps, spb, rows)
}

object Presets {
    private const val ROCK = "Рок"
    private const val POP = "Поп и танцы"
    private const val FUNK = "Фанк"
    private const val HIPHOP = "Хип-хоп"
    private const val BLUES = "Блюз и джаз"
    private const val REGGAE = "Регги и латино"
    private const val HEAVY = "Панк и метал"
    private const val OTHER = "Другое"
    private const val BLANK = "Пустые"

    val all: List<Preset> = listOf(
        // ---------- Рок ----------
        preset(
            "Базовый рок", ROCK, 100,
            kick = "x.......x.......",
            snare = "....X.......X...",
            hat = "x.x.x.x.x.x.x.x.",
        ),
        preset(
            "Рок с двойной бочкой в конце", ROCK, 105,
            kick = "x.......x.x.....",
            snare = "....X.......X...",
            hat = "x.x.x.x.x.x.x.x.",
        ),
        preset(
            "Хард-рок (райд)", ROCK, 120,
            kick = "x.....x.x.......",
            snare = "....X.......X...",
            ride = "x.x.x.x.x.x.x.x.",
        ),
        preset(
            "Рок половинной скорости", ROCK, 80,
            kick = "x.....x.........",
            snare = "........X.......",
            hat = "x.x.x.x.x.x.x.x.",
        ),
        preset(
            "Рок с шестнадцатыми на хэте", ROCK, 95,
            kick = "x.......x.x.....",
            snare = "....X.......X...",
            hat = "XgxgXgxgXgxgXgxg",
        ),
        preset(
            "Кантри (поезд)", ROCK, 140,
            kick = "x.......x.......",
            snare = "x.xgx.xgx.xgx.xg",
        ),
        // ---------- Поп и танцы ----------
        preset(
            "Поп-бит", POP, 110,
            kick = "x...x...x...x...",
            snare = "....X.......X...",
            hat = "x.x.x.x.x.x.x.x.",
        ),
        preset(
            "Диско", POP, 120,
            kick = "x...x...x...x...",
            snare = "....X.......X...",
            hat = "x...x...x...x...",
            open = "..x...x...x...x.",
        ),
        preset(
            "Хаус", POP, 124,
            kick = "X...X...X...X...",
            rim = "....x.......x...",
            open = "..x...x...x...x.",
        ),
        preset(
            "Драм-н-бейс", POP, 170,
            kick = "x.........x.....",
            snare = "....X.......X...",
            hat = "x.x.x.x.x.x.x.x.",
        ),
        // ---------- Фанк ----------
        preset(
            "Фанк с призрачными нотами", FUNK, 100,
            kick = "x.x.......x.x...",
            snare = "....x..g.g..x..g",
            hat = "XgxgXgxgXgxgXgxg",
        ),
        preset(
            "Фанк на шестнадцатых", FUNK, 95,
            kick = "x..x..x...x..x..",
            snare = "....X.......X...",
            hat = "XxgxXxgxXxgxXxgx",
        ),
        // ---------- Хип-хоп ----------
        preset(
            "Бум-бэп", HIPHOP, 90,
            kick = "x.....x..x......",
            snare = "....X.......X...",
            hat = "x.x.x.x.x.x.x.x.",
        ),
        preset(
            "Трэп", HIPHOP, 140,
            kick = "x.......x..x....",
            snare = "........X.......",
            hat = "x.x.x.xxx.x.xxxx",
        ),
        // ---------- Блюз и джаз (триольная сетка: 3 клетки на долю) ----------
        preset(
            "Блюз-шаффл", BLUES, 90, steps = 12, spb = 3,
            kick = "x.....x.....",
            snare = "...X.....X..",
            hat = "x.xx.xx.xx.x",
        ),
        preset(
            "Медленный блюз 12/8", BLUES, 56, steps = 12, spb = 3,
            kick = "X.....x.....",
            snare = "...X.....X..",
            hat = "XgxXgxXgxXgx",
        ),
        preset(
            "Джаз-свинг", BLUES, 130, steps = 12, spb = 3,
            kick = "g..g..g..g..",
            hat = "...x.....x..",
            ride = "x..x.xx..x.x",
        ),
        // ---------- Регги и латино ----------
        preset(
            "Регги (one drop)", REGGAE, 75,
            kick = "........x.......",
            rim = "........x.......",
            hat = "x.x.x.x.x.x.x.x.",
        ),
        preset(
            "Босса-нова", REGGAE, 120,
            kick = "x..x....x..x....",
            rim = "x..x..x...x.x...",
            hat = "x.x.x.x.x.x.x.x.",
        ),
        preset(
            "Ска", REGGAE, 150,
            kick = "x.......x.......",
            snare = "....X.......X...",
            hat = "..x...x...x...x.",
        ),
        // ---------- Панк и метал ----------
        preset(
            "Панк-бит", HEAVY, 170,
            kick = "x...x...x...x...",
            snare = "..x...x...x...x.",
            hat = "x.x.x.x.x.x.x.x.",
        ),
        preset(
            "Метал: двойная бочка", HEAVY, 130,
            kick = "XxxxXxxxXxxxXxxx",
            snare = "....X.......X...",
            ride = "x...x...x...x...",
        ),
        // ---------- Другое ----------
        preset(
            "Баллада", OTHER, 68,
            kick = "x.......x.x.....",
            rim = "....x.......x...",
            hat = "x.x.x.x.x.x.x.x.",
        ),
        preset(
            "Вальс 3/4", OTHER, 120, steps = 12, spb = 4,
            kick = "x...........",
            snare = "....x...x...",
            hat = "x...x...x...",
        ),
        preset(
            "Баллада 6/8", OTHER, 70, steps = 6, spb = 3,
            kick = "X.....",
            snare = "...X..",
            hat = "XgxXgx",
        ),
        // ---------- Пустые ----------
        preset("Пустой такт 4/4 (16 клеток)", BLANK, 100),
        preset("Пустой такт с триолями (12 клеток)", BLANK, 90, steps = 12, spb = 3),
    )
}

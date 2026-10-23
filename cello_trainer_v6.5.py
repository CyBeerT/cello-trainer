#!/usr/bin/env python3
"""Cello Sight-Reading Trainer v6.3 — Python 3.9+ (Tkinter, standard library only).

Run with: python cello_trainer.py

Open-string tuning: C2, G2, D3, A3; reference A4 = 443 Hz.
The position-to-semitone ranges are a configurable first approximation. Compare
and refine POSITION_RANGES against your own Cello Companion chart before relying
on it for advanced/extended positions.
"""
import math, os, random, shutil, struct, subprocess, sys, tempfile, threading, time, wave
import tkinter as tk
from tkinter import ttk, messagebox

A4_HZ = 443.0
STRINGS = [("A", 57), ("D", 50), ("G", 43), ("C", 36)]  # top to bottom
PITCH_NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"]
LETTERS = ["C", "D", "E", "F", "G", "A", "B"]
NATURAL_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
# Semitone distances above each open string. Intentionally editable.
POSITION_RANGES = {
    "Half position": (1, 3),
    "First position": (2, 4),
    "Upper first / lower second": (3, 5),
    "Second position": (4, 6),
    "Third position": (5, 7),
    "Upper third / lower fourth": (6, 8),
    "Fourth position": (7, 9),
    "Fifth position": (9, 11),
    "Sixth position": (10, 12),
    "Seventh position": (12, 14),
}
CLEF_BOTTOM = {"Bass": ("G", 2), "Tenor": ("D", 3), "Treble": ("E", 4)}

def freq_for_midi(midi):
    return A4_HZ * 2 ** ((midi - 69) / 12)

def pitch_name(midi):
    return f"{PITCH_NAMES[midi % 12]}{midi // 12 - 1}"

def diatonic_index(letter, octave):
    return octave * 7 + LETTERS.index(letter)

def natural_pitch(letter, octave):
    return (octave + 1) * 12 + NATURAL_PC[letter]

def midi_to_spelling(midi):
    n = PITCH_NAMES[midi % 12]
    return n[0], ("♯" if "♯" in n else ""), midi // 12 - 1

class TonePlayer:
    def play(self, midi, duration=0.7):
        def run():
            rate = 22050
            count = int(rate * duration)
            fd, path = tempfile.mkstemp(suffix=".wav", prefix="cello_")
            os.close(fd)
            try:
                with wave.open(path, "wb") as wf:
                    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
                    data = bytearray()
                    hz = freq_for_midi(midi)
                    for i in range(count):
                        fade = min(1.0, i / 500, (count - i) / 1800)
                        sample = int(10000 * max(0, fade) * math.sin(2 * math.pi * hz * i / rate))
                        data.extend(struct.pack("<h", sample))
                    wf.writeframes(data)
                if sys.platform.startswith("win"):
                    import winsound
                    winsound.PlaySound(path, winsound.SND_FILENAME)
                elif sys.platform == "darwin" and shutil.which("afplay"):
                    subprocess.run(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif shutil.which("aplay"):
                    subprocess.run(["aplay", "-q", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif shutil.which("paplay"):
                    subprocess.run(["paplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    print(f"Audio player unavailable; target frequency is {hz:.2f} Hz")
            finally:
                try: os.remove(path)
                except OSError: pass
        threading.Thread(target=run, daemon=True).start()

class CelloTrainer:
    def __init__(self, root):
        self.root = root
        root.title("Cello Sight-Reading Trainer v6.1")
        root.geometry("1100x790")
        # Permit smaller displays; scrollable pages handle the remaining content.
        root.minsize(720, 480)
        style = ttk.Style(root)
        style.configure("TButton", font=("TkDefaultFont", 11), padding=(12, 8))
        style.configure("TCheckbutton", font=("TkDefaultFont", 11), padding=(3, 4))
        style.configure("TLabelframe.Label", font=("TkDefaultFont", 10, "bold"))
        self.player = TonePlayer()
        self.session_count = 50
        self.done = self.first_try_correct = self.errors = self.streak = 0
        self.correct_times = []
        self.question_start = None
        self.target = None
        self.answered = False
        self.locations = []
        self.show_settings()

    def clear(self):
        for w in self.root.winfo_children(): w.destroy()

    def show_settings(self):
        self.clear()
        # Put the settings inside a canvas so the whole page remains reachable
        # on shorter screens. The canvas window follows the available width.
        shell = ttk.Frame(self.root)
        shell.pack(fill="both", expand=True)
        canvas = tk.Canvas(shell, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        page = ttk.Frame(canvas, padding=18)
        page_window = canvas.create_window((0, 0), window=page, anchor="nw")
        page.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(page_window, width=e.width))
        # Mouse-wheel scrolling on Windows/macOS and Linux.
        def wheel(event):
            if getattr(event, "delta", 0):
                canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            elif getattr(event, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(1, "units")
        canvas.bind_all("<MouseWheel>", wheel)
        canvas.bind_all("<Button-4>", wheel)
        canvas.bind_all("<Button-5>", wheel)
        ttk.Label(page, text="Cello Sight-Reading Trainer", font=("TkDefaultFont", 22, "bold")).pack(anchor="w")
        ttk.Label(page, text="Practise recognizing staff notes quickly and finding them on the cello.",
                  font=("TkDefaultFont", 11)).pack(anchor="w", pady=(3, 16))
        clefs = ttk.LabelFrame(page, text="Clefs to practise", padding=10); clefs.pack(fill="x", pady=5)
        self.clef_vars = {}
        for c in ("Bass", "Tenor", "Treble"):
            v = tk.BooleanVar(value=(c == "Bass"))
            self.clef_vars[c] = v
            ttk.Checkbutton(clefs, text=f"{c} clef", variable=v).pack(side="left", padx=(0, 20))
        positions = ttk.LabelFrame(page, text="Cello positions (chart-based names)", padding=10)
        positions.pack(fill="both", expand=True, pady=5)
        self.pos_vars = {}
        grid = ttk.Frame(positions); grid.pack(fill="both", expand=True)
        for i, name in enumerate(POSITION_RANGES):
            v = tk.BooleanVar(value=i < 3); self.pos_vars[name] = v
            ttk.Checkbutton(grid, text=name, variable=v).grid(row=i//3, column=i%3, sticky="w", padx=8, pady=4)
        options = ttk.LabelFrame(page, text="Exercise options", padding=10); options.pack(fill="x", pady=5)
        r = ttk.Frame(options); r.pack(fill="x", pady=3)
        ttk.Label(r, text="Register:").pack(side="left")
        self.range_var = tk.StringVar(value="Full cello range (C2–A5)")
        ttk.Combobox(r, textvariable=self.range_var, state="readonly", width=25,
            values=["Full cello range (C2–A5)", "Lower (C2–G3)", "Middle (G2–D5)", "Upper (C4–A5)"]).pack(side="left", padx=7)
        ttk.Label(r, text="Answer mode:").pack(side="left", padx=(18, 0))
        self.mode_var = tk.StringVar(value="Both")
        ttk.Combobox(r, textvariable=self.mode_var, state="readonly", width=24,
            values=["Both", "Visible note markers", "Continuous clicking"]).pack(side="left", padx=7)
        r2 = ttk.Frame(options); r2.pack(fill="x", pady=3)
        self.lines_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(r2, text="Show subtle fret-like lines (no note names)", variable=self.lines_var).pack(side="left")
        ttk.Label(r2, text="Session:").pack(side="left", padx=(18, 4))
        self.count_var = tk.StringVar(value="50 notes")
        ttk.Combobox(r2, textvariable=self.count_var, state="readonly", width=16,
            values=["20 notes", "50 notes", "100 notes", "Unlimited"]).pack(side="left")
        self.adaptive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="Adaptive practice (repeat missed/slow notes more often)", variable=self.adaptive_var).pack(anchor="w", pady=(4, 0))
        ttk.Label(page, text="Tuning: A4 = 443 Hz  •  open strings: C2, G2, D3, A3",
                  foreground="#555").pack(anchor="w", pady=(8, 2))
        ttk.Label(page, text="Position ranges are editable approximations in this prototype; refine them against your chart.",
                  foreground="#8a5a22", wraplength=900).pack(anchor="w", pady=(0, 8))
        ttk.Button(page, text="Start practice  →", command=self.start).pack(anchor="e", ipadx=20, ipady=9, pady=(4, 8))

    def start(self):
        # Remove settings-page wheel handlers before showing the exercise.
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.unbind_all(sequence)
        selected_clefs = [c for c, v in self.clef_vars.items() if v.get()]
        selected_positions = [p for p, v in self.pos_vars.items() if v.get()]
        if not selected_clefs or not selected_positions:
            messagebox.showwarning("Settings incomplete", "Select at least one clef and one position.")
            return
        self.settings = {
            "clefs": selected_clefs, "positions": selected_positions,
            "range": self.range_var.get(), "mode": self.mode_var.get(),
            "lines": self.lines_var.get(), "adaptive": self.adaptive_var.get()
        }
        self.session_count = {"20 notes":20, "50 notes":50, "100 notes":100, "Unlimited":None}[self.count_var.get()]
        self.done = self.first_try_correct = self.errors = self.streak = 0
        self.correct_times = []; self.mistake_counts = {}
        self.show_game(); self.new_question()

    def show_game(self):
        self.clear()
        header = ttk.Frame(self.root, padding=(14, 10)); header.pack(fill="x")
        ttk.Label(header, text="Cello Sight-Reading", font=("TkDefaultFont", 17, "bold")).pack(side="left")
        ttk.Button(header, text="Settings", command=self.show_settings).pack(side="right")
        self.stats = ttk.Label(self.root, text="Notes 0/50  •  Success 0%  •  Avg —  •  Last —  •  Streak 0",
                               font=("TkDefaultFont", 10))
        self.stats.pack(anchor="e", padx=18)
        # A compact white music panel, centred in the window. Keep the panel
        # narrower than the fingerboard while allowing it to shrink on small screens.
        staff_holder = ttk.Frame(self.root)
        staff_holder.pack(fill="x", pady=(8, 4))
        self.staff = tk.Canvas(staff_holder, width=600, height=155, bg="#fffdf8",
                               highlightthickness=1, highlightbackground="#ddd")
        self.staff.pack(anchor="center")
        def fit_staff(event):
            self.staff.configure(width=max(320, min(600, event.width - 24)))
        staff_holder.bind("<Configure>", fit_staff)
        self.prompt = ttk.Label(self.root, text="Find the note on the fingerboard", font=("TkDefaultFont", 12, "bold"))
        self.prompt.pack(pady=4)
        self.feedback = ttk.Label(self.root, text="Click the matching pitch on a string.", font=("TkDefaultFont", 10))
        self.feedback.pack(pady=2)
        ttk.Label(self.root, text="CELLO FINGERBOARD  •  A / D / G / C strings", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", padx=20, pady=(6, 2))
        self.board = tk.Canvas(self.root, height=310, bg="#241a16", highlightthickness=1, highlightbackground="#555")
        self.board.pack(fill="both", expand=True, padx=18, pady=4)
        self.board.bind("<Configure>", lambda e: self.draw_board())
        bottom = ttk.Frame(self.root, padding=(18, 8, 18, 12)); bottom.pack(fill="x")
        ttk.Button(bottom, text="Play note", command=self.play_note).pack(side="left")
        ttk.Button(bottom, text="Reveal answer", command=self.reveal).pack(side="left", padx=8)
        self.next_button = ttk.Button(bottom, text="Next now →", command=self.new_question, state="disabled")
        self.next_button.pack(side="right")
        self.staff.bind("<Configure>", lambda e: self.draw_staff())

    def pitch_range(self):
        r = self.settings["range"]
        if r.startswith("Lower"): return 36, 55
        if r.startswith("Middle"): return 43, 74
        if r.startswith("Upper"): return 60, 81
        return 36, 81

    def permitted_pitches(self):
        lo, hi = self.pitch_range()
        pitches = set()
        for _string, open_midi in STRINGS:
            if lo <= open_midi <= hi: pitches.add(open_midi)
            for pos in self.settings["positions"]:
                a, b = POSITION_RANGES[pos]
                pitches.update(p for p in range(open_midi+a, open_midi+b+1) if lo <= p <= hi)
        return sorted(pitches)

    def clef_for_target(self):
        m = self.target
        # If multiple clefs are selected, choose a comfortable clef based on register.
        if m < 60 and "Bass" in self.settings["clefs"]: return "Bass"
        if 60 <= m <= 71 and "Tenor" in self.settings["clefs"]: return "Tenor"
        if "Treble" in self.settings["clefs"]: return "Treble"
        if "Tenor" in self.settings["clefs"]: return "Tenor"
        return self.settings["clefs"][0]

    def new_question(self):
        if self.session_count is not None and self.done >= self.session_count:
            self.show_results(); return
        pitches = self.permitted_pitches()
        if not pitches:
            messagebox.showwarning("No notes", "No notes fit these settings. Try a wider register or more positions.")
            return
        if self.settings["adaptive"] and getattr(self, "mistake_counts", None):
            weighted = []
            for p in pitches:
                weighted.extend([p] * (1 + min(4, self.mistake_counts.get(p, 0))))
            self.target = random.choice(weighted)
        else:
            self.target = random.choice(pitches)
        self.answered = False; self.first_attempt = True
        self.locations = self.find_locations(self.target)
        self.question_start = time.perf_counter()
        self.feedback.config(text="Click the matching pitch on a string.", foreground="#333")
        self.next_button.config(state="disabled")
        self.draw_staff(); self.draw_board(); self.update_stats()

    def draw_staff(self):
        if not hasattr(self, "staff") or not self.staff.winfo_exists() or self.target is None: return
        c = self.staff; c.delete("all")
        w = max(c.winfo_width(), 420)
        h = max(c.winfo_height(), 150)
        clef = self.clef_for_target()
        # The canvas itself is the narrower white panel; staff lines use most
        # of that panel, with a little room for the clef and ledger lines.
        staff_width = min(w - 105, 470)
        left = max(54, (w - staff_width) / 2)
        right = left + staff_width
        top, spacing = 37, 13
        for i in range(5):
            y = top + i*spacing
            c.create_line(left, y, right, y, fill="#333", width=1.4)
        clef_symbol = {"Bass":"𝄢", "Tenor":"𝄡", "Treble":"𝄞"}[clef]
        # The tenor C-clef's center marks the fourth line from the bottom,
        # which is the same staff line surrounded by the bass-clef dots.
        # Staff lines are spaced 13 px apart, so this is the second line from top.
        clef_y = top + spacing if clef == "Tenor" else top + 26
        c.create_text(left-34, clef_y, text=clef_symbol, font=("DejaVu Sans", 43), fill="#222")
        letter, accidental, octave = midi_to_spelling(self.target)
        step = diatonic_index(letter, octave)
        base_letter, base_octave = CLEF_BOTTOM[clef]
        delta = step - diatonic_index(base_letter, base_octave)
        x = (left+right)/2
        y = top + 4*spacing - delta*spacing/2
        # Ledger lines
        if y < top-1:
            ly = top-spacing
            while ly >= y-2:
                c.create_line(x-23, ly, x+23, ly, fill="#555", width=1.4); ly -= spacing
        if y > top+4*spacing+1:
            ly = top+5*spacing
            while ly <= y+2:
                c.create_line(x-23, ly, x+23, ly, fill="#555", width=1.4); ly += spacing
        # Natural pitch represented by the note's letter/octave; display accidental if needed.
        natural_midi = natural_pitch(letter, octave)
        accidental_value = self.target - natural_midi
        if accidental_value == 1: accidental = "♯"
        elif accidental_value == 2: accidental = "𝄪"
        elif accidental_value == -1: accidental = "♭"
        elif accidental_value == -2: accidental = "𝄫"
        else: accidental = ""
        if accidental: c.create_text(x-34, y, text=accidental, font=("DejaVu Sans", 22, "bold"), fill="#111")
        # Notehead is sized relative to staff spacing. This leaves clearer
        # separation between adjacent staff steps (especially in imagined chords).
        c.create_oval(x-9, y-5.5, x+9, y+5.5, fill="#111", outline="#111", width=1.2)
        c.create_text(w-10, 15, text=f"{clef} clef", anchor="e", fill="#555", font=("TkDefaultFont", 9))
        self.prompt.config(text=f"Identify the note in {clef} clef")

    def geometry(self):
        # The diagram runs left-to-right from nut toward bridge/body. The four
        # strings spread slightly as they approach the bridge, like a real cello.
        w = max(self.board.winfo_width(), 600); h = max(self.board.winfo_height(), 260)
        left, right = 75, w-35
        center = h * 0.48
        top, bottom = center-58, center+58  # generous click area around the strings
        return w, h, left, right, top, bottom

    def x_for_semitone(self, semitones, left, right):
        # Equal-tempered string length: positions get closer toward the bridge.
        return left + (right-left)*(1 - 2**(-semitones/12))

    def pitch_at_x(self, open_midi, x, left, right):
        f = min(.985, max(0, (x-left)/(right-left)))
        return open_midi + round(-12*math.log2(max(.001, 1-f)))

    def string_y(self, idx, x, left, right, top, bottom):
        # String spacing opens from a narrow neck (~4 cm) toward the wider
        # bridge/body area (~7 cm); the schematic uses the same perspective.
        t = min(1.0, max(0.0, (x-left)/(right-left)))
        spacing = 18 + 12*t
        center = (top+bottom)/2
        return center + (idx-1.5)*spacing

    def find_locations(self, midi):
        _, _, left, right, top, bottom = self.geometry()
        lo, hi = self.pitch_range()
        result = []
        for idx, (_name, open_midi) in enumerate(STRINGS):
            semis = midi-open_midi
            if semis < 0 or semis > 24 or not (lo <= midi <= hi): continue
            valid = semis == 0 or any(POSITION_RANGES[p][0] <= semis <= POSITION_RANGES[p][1] for p in self.settings["positions"])
            if valid:
                x = self.x_for_semitone(semis, left, right)
                y = self.string_y(idx, x, left, right, top, bottom)
                result.append((idx, midi, x, y))
        return result

    def draw_board(self):
        if not hasattr(self, "board") or not self.board.winfo_exists(): return
        c = self.board; c.delete("all")
        w,h,left,right,top,bottom = self.geometry()
        center = (top+bottom)/2
        # Dark display surround.
        c.create_rectangle(18, 12, w-18, h-12, fill="#2a201c", outline="#80624e", width=2)
        # Cello-shaped body: broad upper/lower bouts, a pinched C-bout waist,
        # and rounded shoulders. The body begins around the fourth-position
        # region, beginning around F on the A string.
        # Start the cello body at the 8th semitone from the nut: F on the A string.
        body_start = self.x_for_semitone(8, left, right)
        body_end = min(w-27, right+34)
        # Sideways cello silhouette inspired by the supplied position chart:
        # rounded upper/lower bouts, distinct shoulders, and a deeper C-bout waist.
        # The original chart is a photo rather than a clean vector outline, so this
        # is a hand-drawn approximation of its visible instrument contour.
        body_points = [
            body_start, center-24,
            body_start+12, center-48,
            body_start+38, center-66,
            body_start+78, center-78,
            body_end-74, center-79,
            body_end-34, center-68,
            body_end-9, center-48,
            body_end, center-29,
            body_end-8, center-17,
            body_end-27, center-10,
            body_end-37, center-4,
            body_end-37, center+4,
            body_end-27, center+10,
            body_end-8, center+17,
            body_end, center+29,
            body_end-9, center+48,
            body_end-34, center+68,
            body_end-74, center+79,
            body_start+78, center+78,
            body_start+38, center+66,
            body_start+12, center+48,
            body_start, center+24,
        ]
        c.create_polygon(body_points, smooth=True, splinesteps=18,
                         fill="#704a35", outline="#c09367", width=2.5)
        # Subtle C-bout / waist details make the silhouette read more like a cello.
        c.create_arc(body_start+25, center-28, body_start+70, center+28,
                     start=75, extent=210, style="arc", outline="#c09367", width=1.4)
        c.create_arc(body_end-65, center-28, body_end-20, center+28,
                     start=255, extent=210, style="arc", outline="#c09367", width=1.4)
        # Pegbox and four tuning pegs at the top end, beyond the nut. Since this
        # diagram runs horizontally, the pegbox extends to the left and pegs
        # alternate above/below it, as on a real cello head.
        pegbox_top = center-24
        pegbox_bottom = center+24
        c.create_polygon(left-38, center-17, left-20, center-25,
                         left+2, center-21, left+2, center+21,
                         left-20, center+25, left-38, center+17,
                         smooth=True, fill="#704a35", outline="#c09367", width=2)
        for i, py in enumerate((center-17, center-6, center+6, center+17)):
            side = -1 if i % 2 == 0 else 1
            peg_x = left-24
            peg_end_x = left-48
            peg_end_y = py + side*10
            c.create_line(peg_x, py, peg_end_x, peg_end_y,
                          fill="#b58b61", width=4, capstyle=tk.ROUND)
            c.create_oval(peg_end_x-4, peg_end_y-4, peg_end_x+4, peg_end_y+4,
                          fill="#3a261c", outline="#c09367", width=1.5)
        # Narrow neck widening toward the bridge. The strings and position
        # guides follow this taper rather than being perpendicular to the board.
        neck_top_left = self.string_y(0, left, left, right, top, bottom)-10
        neck_bottom_left = self.string_y(3, left, left, right, top, bottom)+10
        neck_top_right = self.string_y(0, right, left, right, top, bottom)-10
        neck_bottom_right = self.string_y(3, right, left, right, top, bottom)+10
        c.create_polygon(left, neck_top_left, right, neck_top_right,
                         right, neck_bottom_right, left, neck_bottom_left,
                         fill="#211815", outline="#a08168", width=2)
        # Nut and subtle position guides, angled to match the fingerboard taper.
        c.create_line(left, neck_top_left, left, neck_bottom_left, fill="#e1d4c2", width=4)
        if self.settings["lines"]:
            for semi in range(1, 19):
                # Leave out selected position-guide lines to reduce visual clutter.
                if semi in {1, 3, 6, 8, 10, 13}:
                    continue
                x = self.x_for_semitone(semi, left, right)
                y0 = self.string_y(0, x, left, right, top, bottom)-8
                y1 = self.string_y(3, x, left, right, top, bottom)+8
                c.create_line(x, y0, x, y1, fill="#604a3e", width=1)
                # Small position label placed just above the fingerboard.
                if semi == POSITION_RANGES["Fourth position"][0]:
                    c.create_text(x, y0 - 5, text="4", anchor="s",
                                  fill="#e1d4c2", font=("TkDefaultFont", 8, "bold"))
        for idx, (name, open_midi) in enumerate(STRINGS):
            y_left = self.string_y(idx, left, left, right, top, bottom)
            y_right = self.string_y(idx, right, left, right, top, bottom)
            string_width = {"A": 1.0, "D": 1.6, "G": 2.3, "C": 3.0}[name]  # A thinnest, C thickest
            c.create_line(left, y_left, right, y_right, fill="#d7c9b5", width=string_width)
            # Visible marker mode: show pitch markers, never note names.
            if not self.answered and self.settings["mode"] != "Continuous clicking":
                for semi in range(0, 25):
                    x = self.x_for_semitone(semi, left, right)
                    if x <= right:
                        y = self.string_y(idx, x, left, right, top, bottom)
                        c.create_oval(x-2.5, y-2.5, x+2.5, y+2.5, outline="#927865", width=1)
        if self.answered:
            for idx, midi, x, y in self.locations:
                c.create_oval(x-10, y-10, x+10, y+10, fill="#42df89", outline="white", width=2)
                c.create_text(x, y-20, text=pitch_name(midi), fill="white", font=("TkDefaultFont", 9, "bold"))
        c.bind("<Button-1>", self.on_click)

    def on_click(self, event):
        if self.answered or self.target is None: return
        _, _, left, right, top, bottom = self.geometry()
        if not (left <= event.x <= right): return
        # Choose the nearest of the four slightly fanned strings at this x.
        candidates = [self.string_y(i, event.x, left, right, top, bottom) for i in range(4)]
        idx = min(range(4), key=lambda i: abs(event.y-candidates[i]))
        if abs(event.y-candidates[idx]) > 13: return
        clicked = self.pitch_at_x(STRINGS[idx][1], event.x, left, right)
        if clicked == self.target:
            self.finish_correct()
        else:
            self.errors += 1; self.streak = 0; self.first_attempt = False
            self.mistake_counts[self.target] = self.mistake_counts.get(self.target, 0) + 1
            self.feedback.config(text=f"Not quite — that position sounds like {pitch_name(clicked)}. Try again.", foreground="#b13b32")
            self.update_stats()

    def finish_correct(self):
        if self.answered: return
        elapsed = time.perf_counter() - self.question_start
        self.answered = True; self.done += 1
        if self.first_attempt:
            self.first_try_correct += 1
        self.correct_times.append(elapsed)
        self.streak += 1
        self.feedback.config(text=f"Correct — {pitch_name(self.target)}. All valid positions are highlighted.", foreground="#167544")
        self.next_button.config(state="normal")
        self.play_note(); self.draw_board(); self.update_stats()
        # Keep the exercise flowing: move to the next note automatically, while
        # leaving a short moment to see the feedback and highlighted locations.
        self.root.after(650, self.advance_if_answered)

    def advance_if_answered(self):
        if self.answered and hasattr(self, "staff") and self.staff.winfo_exists():
            self.new_question()

    def reveal(self):
        if self.target is None or self.answered: return
        self.answered = True
        # Revealed notes count as completed but not as first-try successes.
        self.done += 1
        self.streak = 0
        self.feedback.config(text=f"Answer: {pitch_name(self.target)}. Green circles show valid locations in the selected range.", foreground="#245d8e")
        self.next_button.config(state="normal"); self.draw_board(); self.update_stats()
        self.root.after(650, self.advance_if_answered)

    def play_note(self):
        if self.target is not None: self.player.play(self.target)

    def update_stats(self):
        if not hasattr(self, "stats"): return
        rate = (100*self.first_try_correct/self.done) if self.done else 0
        avg = sum(self.correct_times)/len(self.correct_times) if self.correct_times else None
        last = self.correct_times[-1] if self.correct_times else None
        limit = "∞" if self.session_count is None else str(self.session_count)
        self.stats.config(text=f"Notes {self.done}/{limit}  •  First-try success {rate:.0f}%  •  Avg {avg:.2f}s" if avg is not None else f"Notes {self.done}/{limit}  •  First-try success {rate:.0f}%  •  Avg —")
        suffix = f"  •  Last {last:.2f}s" if last is not None else ""
        self.stats.config(text=self.stats.cget("text") + suffix + f"  •  Errors {self.errors}  •  Streak {self.streak}")

    def show_results(self):
        self.clear()
        page = ttk.Frame(self.root, padding=30); page.pack(fill="both", expand=True)
        ttk.Label(page, text="Session complete!", font=("TkDefaultFont", 22, "bold")).pack(anchor="w", pady=(0, 16))
        rate = 100*self.first_try_correct/self.done if self.done else 0
        avg = sum(self.correct_times)/len(self.correct_times) if self.correct_times else 0
        best = min(self.correct_times) if self.correct_times else 0
        for label, value in [
            ("Notes completed", str(self.done)),
            ("First-attempt success rate", f"{rate:.1f}%"),
            ("Average correct reaction time", f"{avg:.2f} s" if avg else "—"),
            ("Fastest correct reaction", f"{best:.2f} s" if best else "—"),
            ("Incorrect clicks", str(self.errors)),
        ]:
            row = ttk.Frame(page); row.pack(fill="x", pady=6)
            ttk.Label(row, text=label, font=("TkDefaultFont", 12)).pack(side="left")
            ttk.Label(row, text=value, font=("TkDefaultFont", 12, "bold")).pack(side="right")
        ttk.Button(page, text="Practise again", command=self.show_settings).pack(anchor="e", pady=20)

def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "clam" in style.theme_names(): style.theme_use("clam")
    except tk.TclError:
        pass
    CelloTrainer(root)
    root.mainloop()

if __name__ == "__main__":
    main()

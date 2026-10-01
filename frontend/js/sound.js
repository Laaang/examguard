/**
 * ExamGuard DNS - Audio Synthesizer (Web Audio API)
 * Generira zvučne signale za alarme i prijavu bez vanjskih MP3 datoteka.
 */
class SoundManager {
  constructor() {
    this.audioCtx = null;
    this.isMuted = localStorage.getItem('examguard_muted') === 'true';
  }

  _initContext() {
    if (!this.audioCtx) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        this.audioCtx = new AudioContext();
      }
    }
    if (this.audioCtx && this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }
  }

  toggleMute() {
    this.isMuted = !this.isMuted;
    localStorage.setItem('examguard_muted', this.isMuted);
    return this.isMuted;
  }

  playViolationAlarm() {
    if (this.isMuted) return;
    try {
      this._initContext();
      if (!this.audioCtx) return;

      const now = this.audioCtx.currentTime;
      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();

      osc.type = 'sawtooth';
      // Alarmni ton: nagli skok 880Hz -> 440Hz -> 880Hz
      osc.frequency.setValueAtTime(880, now);
      osc.frequency.exponentialRampToValueAtTime(440, now + 0.15);
      osc.frequency.setValueAtTime(880, now + 0.2);
      osc.frequency.exponentialRampToValueAtTime(440, now + 0.35);

      gain.gain.setValueAtTime(0.2, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.45);

      osc.connect(gain);
      gain.connect(this.audioCtx.destination);

      osc.start(now);
      osc.stop(now + 0.45);
    } catch (e) {
      console.warn("Audio playback not allowed yet:", e);
    }
  }

  playSuccessCheckin() {
    if (this.isMuted) return;
    try {
      this._initContext();
      if (!this.audioCtx) return;

      const now = this.audioCtx.currentTime;
      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();

      osc.type = 'sine';
      // Blagi ugodni ton za prijavu studenta: 523Hz (C5) -> 659Hz (E5)
      osc.frequency.setValueAtTime(523.25, now);
      osc.frequency.exponentialRampToValueAtTime(659.25, now + 0.12);

      gain.gain.setValueAtTime(0.15, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.3);

      osc.connect(gain);
      gain.connect(this.audioCtx.destination);

      osc.start(now);
      osc.stop(now + 0.3);
    } catch (e) {
      console.warn("Audio playback not allowed:", e);
    }
  }
}

window.soundManager = new SoundManager();

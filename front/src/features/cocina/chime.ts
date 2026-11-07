/**
 * Chime suave para pedidos nuevos, sintetizado con Web Audio (sin archivos).
 * Los navegadores solo permiten sonar después de un gesto del usuario: la
 * pantalla pide activarlo una vez con un toque.
 */
let ctx: AudioContext | null = null;

export function unlockAudio(): boolean {
  try {
    ctx ??= new AudioContext();
    if (ctx.state === "suspended") void ctx.resume();
    return true;
  } catch {
    return false;
  }
}

export function chime() {
  if (!ctx || ctx.state !== "running") return;
  const now = ctx.currentTime;
  // Dos notas cortas (quinta justa), con ataque y caída suaves
  [659.25, 987.77].forEach((freq, i) => {
    const osc = ctx!.createOscillator();
    const gain = ctx!.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    const t = now + i * 0.14;
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(0.18, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.9);
    osc.connect(gain).connect(ctx!.destination);
    osc.start(t);
    osc.stop(t + 1);
  });
}

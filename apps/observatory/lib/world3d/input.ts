export const playInput = {
  keys: new Set<string>(),
  joyX: 0,
  joyY: 0,
  sprint: false,
  interactQueued: false
};

const MOVE_KEYS = new Set([
  "KeyW", "KeyA", "KeyS", "KeyD",
  "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"
]);

export function attachPlayInput(): () => void {
  const down = (event: KeyboardEvent) => {
    if (MOVE_KEYS.has(event.code)) event.preventDefault();
    playInput.keys.add(event.code);
    if ((event.code === "ShiftLeft" || event.code === "ShiftRight") && !event.repeat) {
      playInput.sprint = true;
    }
    if (event.code === "KeyE" && !event.repeat) playInput.interactQueued = true;
  };
  const up = (event: KeyboardEvent) => {
    playInput.keys.delete(event.code);
    if (event.code === "ShiftLeft" || event.code === "ShiftRight") playInput.sprint = false;
  };
  const blur = () => {
    playInput.keys.clear();
    playInput.sprint = false;
    playInput.joyX = 0;
    playInput.joyY = 0;
  };

  window.addEventListener("keydown", down, { passive: false });
  window.addEventListener("keyup", up);
  window.addEventListener("blur", blur);
  return () => {
    window.removeEventListener("keydown", down);
    window.removeEventListener("keyup", up);
    window.removeEventListener("blur", blur);
  };
}

export function moveAxes(): { x: number; z: number } {
  let x = (playInput.keys.has("KeyD") || playInput.keys.has("ArrowRight") ? 1 : 0) -
    (playInput.keys.has("KeyA") || playInput.keys.has("ArrowLeft") ? 1 : 0);
  let z = (playInput.keys.has("KeyS") || playInput.keys.has("ArrowDown") ? 1 : 0) -
    (playInput.keys.has("KeyW") || playInput.keys.has("ArrowUp") ? 1 : 0);
  x += playInput.joyX;
  z += playInput.joyY;
  const length = Math.hypot(x, z);
  if (length > 1) {
    x /= length;
    z /= length;
  }
  return { x, z };
}

export function consumeInteract(): boolean {
  const queued = playInput.interactQueued;
  playInput.interactQueued = false;
  return queued;
}

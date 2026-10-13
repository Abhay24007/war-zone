# WAR ZONE - 2D Battle Arena (pygame)

Top-down deathmatch arena with a Deadshot.io-style dark/amber interface:
menu with nickname + loadout, crosshair, minimap, kill feed, ammo/health HUD, scoreboard.
Python + pygame, served to the browser on localhost with **pygbag**.

## Run it as a website on localhost

```bash
pip install pygame pygbag
cd war_zone
pygbag .
```

Then open **http://localhost:8000** and click the page once (browsers need a click
before the game can take keyboard/mouse input).

The first launch downloads the pygame web runtime (needs internet once).

## Or run it as a desktop window

```bash
pip install pygame
python main.py
```

## Controls

| Key / Mouse        | Action                  |
|--------------------|-------------------------|
| W A S D / arrows   | Move                    |
| Mouse              | Aim                     |
| Left click         | Shoot (hold for rifle)  |
| R                  | Reload                  |
| 1 / 2 / 3, wheel   | Rifle / Shotgun / Sniper|
| Shift              | Dash (2s cooldown)      |
| Tab (or Q) hold    | Scoreboard              |
| Esc                | Pause (M = quit to menu)|

## Rules

- First to 20 kills or 3 minutes, highest kills wins.
- Green crosses restore 40 HP (respawn after 15s).
- Respawn after 3s with 1.5s spawn protection.
- Choose 3, 5 or 7 bots in the menu.

## Tweaking

Everything lives in `main.py`: weapon stats in `WEAPONS`, arena walls in `OBST`,
match length and kill limit at the top (`MATCH_TIME`, `KILL_LIMIT`).

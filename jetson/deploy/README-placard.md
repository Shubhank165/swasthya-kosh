# The panel placard

`medikiosk.edge.placard` puts two things on the kiosk's 2.8" panel when the intake loop is not
driving it: whatever entry details the event wants on show, and the address the tablet should be
pointed at. The address it discovers itself. The entry details it reads from a file.

That file is deliberately not in this repository. Entry details name a team and an event, they
change every time, and a public repo is the wrong place for them.

Copy the example and fill it in, on the board itself:

    mkdir -p ~/.config/medikiosk
    cp jetson/deploy/placard.example.json ~/.config/medikiosk/placard.json
    $EDITOR ~/.config/medikiosk/placard.json

A list of `[label, value]` pairs, rendered top to bottom in the order given. Or point
`MEDIKIOSK_PLACARD_ENTRY` at a file somewhere else — the systemd unit is the place to set it if
the service runs as a different user.

With no file installed the placard renders a neutral placeholder, so `--png` works on a fresh
clone and the service never crashes for want of paperwork.

    python3 -m medikiosk.edge.placard --png /tmp/card.png --scale 3

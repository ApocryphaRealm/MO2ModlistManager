r"""Live check on a SCRATCH Mod Organizer 2: Apply, then "Undo this Apply" pressed AT ONCE - the sequence that raised
MO2's Error window "failed to write mod list: invalid mod index" (2026-11-20). No mouse and no keyboard: MO2 is driven
through MO2 Agent Control 1.1.0 or newer (its mo2_ctl.py, the window commands).

    python tools\live_fast_undo.py --instance "<scratch MO2 folder>" --ctl "<path to mo2_ctl.py>"
           [--profile Default] [--rounds 3] [--pause 0] [--expect-error]

MO2 must be running on the instance with Modlist Manager and MO2 Agent Control installed, the profile in a state where
Apply asks its "Plugins would be switched off" question. Each round: Apply -> answer (the two Apply answers in turn)
-> wait --pause seconds -> Undo, then:
  - whether an Error window appeared (the modal left open after the Undo press),
  - how many new "failed to write mod list" lines MO2's log gained,
  - whether modlist.txt, plugins.txt and loadorder.txt are byte-identical to the start.
Exit 0: no Error window, no new log line, files identical in every round. With --expect-error (the control, run on a
build WITHOUT the fix, --pause 0): exit 0 when the Error window DID appear in every round - the fault is reproduced by
timing alone. An Error window met along the way is answered OK so the run can go on, and is always reported.
"""
import argparse, hashlib, importlib.util, json, os, sys, time

MM = "MO2 Modlist Manager"
QUESTION = "Plugins would be switched off"
ANSWERS = ("Apply, leave plugins as they are", "Apply and switch them off")
FILES = ("modlist.txt", "plugins.txt", "loadorder.txt")


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--instance", required=True)
    p.add_argument("--ctl", required=True, help="MO2 Agent Control's mo2_ctl.py")
    p.add_argument("--profile", default="Default")
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--pause", type=float, default=0.0, help="seconds between Apply's answer and the Undo press")
    p.add_argument("--expect-error", action="store_true")
    a = p.parse_args(argv)
    low = os.path.normcase(os.path.abspath(a.instance))
    if "scratch" not in low and "_work" not in low:
        print("refused: this presses Apply. Run it on a scratch instance (a path holding 'scratch' or '_work').")
        return 2
    spec = importlib.util.spec_from_file_location("mo2_ctl", a.ctl)
    ctl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ctl)

    def call(cmd, **args):
        ch, why = ctl.channel(a.instance)
        if not ch:
            raise SystemExit("no channel: " + why)
        return ctl.send(ch, {"token": ch["token"], "cmd": cmd, "args": args}, 120)

    prof = os.path.join(a.instance, "profiles", a.profile)

    def digest():
        return {f: hashlib.sha256(open(os.path.join(prof, f), "rb").read()).hexdigest()[:16] for f in FILES}

    mo_log = os.path.join(a.instance, "logs", "mo_interface.log")

    def log_errors():
        try:
            return open(mo_log, encoding="utf-8", errors="replace").read().count("failed to write mod list")
        except OSError:
            return 0

    def modal_title(r):
        return ((r or {}).get("modal") or {}).get("title")

    def wait_button(text, timeout=90):
        t0 = time.time()
        while time.time() - t0 < timeout:
            t = call("ui_tree")
            if modal_title(t) == MM and any(c.get("kind") == "button" and c.get("text") == text and c.get("enabled")
                                           for c in t.get("controls", [])):
                return True
            time.sleep(0.5)
        return False

    info = call("info")
    print("MO2 Agent Control", info.get("version"), "| profile", info.get("profile"))
    t = call("ui_tree")
    if modal_title(t) != MM:
        r = call("ui_click", name="MO2ModlistManagerBtn")
        if modal_title(r) != MM:
            print("FAIL: the Modlist Manager window did not open:", json.dumps(r)[:300])
            return 1
    if not wait_button("Apply"):
        print("FAIL: Apply never became available")
        return 1
    pre = digest()
    rounds, bad = [], 0
    for i in range(a.rounds):
        answer = ANSWERS[i % 2]
        before = log_errors()
        r = call("ui_click", text="Apply")
        if modal_title(r) != QUESTION:
            print("FAIL: Apply did not ask its question:", json.dumps(r)[:300])
            return 1
        r = call("ui_answer_modal", text=answer, expect=QUESTION)
        t_apply = time.time()
        if a.pause:
            time.sleep(a.pause)
        r = call("ui_click", text="Undo this Apply")
        gap = time.time() - t_apply
        if not r.get("ok"):                       # the button is not there yet: the Apply is still finishing
            wait_button("Undo this Apply", 20)
            r = call("ui_click", text="Undo this Apply")
            gap = time.time() - t_apply
        title = modal_title(r)
        error_box = title not in (MM, None)
        box = None
        if error_box:
            box = {"title": title, "text": (r.get("modal") or {}).get("text")}
            call("ui_answer_modal", text=(r["modal"]["buttons"][0]["text"]), expect=title)
        time.sleep(1.5)                           # MO2's own later save, if any, has been written by now
        new_lines = log_errors() - before
        same = digest() == pre
        rounds.append({"round": i + 1, "answer": answer, "undo_after_s": round(gap, 2), "error_window": box,
                       "new_log_errors": new_lines, "files_identical": same})
        print(json.dumps(rounds[-1], ensure_ascii=False))
        clean = (not error_box) and new_lines == 0 and same
        if a.expect_error:
            bad += 0 if (error_box and new_lines > 0) else 1
        else:
            bad += 0 if clean else 1
        if not wait_button("Apply", 60):
            print("FAIL: Apply did not come back after the Undo")
            return 1
    r = call("ui_click", text="Close")
    print("closed:", r.get("ok"), "| modal left:", modal_title(call("ui_tree")))
    final = digest() == pre
    verdict = "PASS" if not bad and (final or a.expect_error) else "FAIL"
    what = "the Error window was reproduced in every round" if a.expect_error else "no Error window, no log error, files identical"
    print(f"{verdict}: {a.rounds - bad}/{a.rounds} rounds - {what}; profile identical at the end: {final}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

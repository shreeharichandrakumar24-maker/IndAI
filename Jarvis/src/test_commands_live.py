"""Live scripted multi-turn test for the four composite Jarvis tools.

Run (backend must be up):  venv/Scripts/python.exe src/test_commands_live.py
Prints the spoken sentence each turn would produce and PASS/FAIL. Creates only
temp rows and undoes them.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def pw(text, n=160):
    s = str(text)
    return s if len(s) <= n else s[:n] + "..."


async def main():
    import tools as T
    inst = T.IndAITools(lambda: None)
    by_name = {getattr(t, "id", getattr(t, "__name__", "?")): t for t in inst.tools()}
    results = []

    def check(name, ok, out):
        results.append((name, bool(ok)))
        print(f"{'PASS' if ok else 'FAIL'} {name}\n     say: {pw(out)}")

    # Turn 1: "assign a CNC operation task to Ravi Kumar" -> done in one turn.
    r = await by_name["do_assign_task"](None, person="Ravi Kumar", task_text="CNC operation")
    check("turn1 assign CNC to Ravi Kumar (no questions)", "Done:" in r and "?" not in r, r)

    # Turn 2: "undo that"
    r2 = await by_name["undo_last"](None)
    check("turn2 undo that", "Undone" in r2 or "nothing recent" in r2.lower(), r2)

    # Turn 3: "create an order for 50 gear housings for Acme and make anything
    #          by yourself"
    r3 = await by_name["do_create_order"](None, product="gear housings", quantity=50,
                                          customer="Acme", autopilot=True)
    check("turn3 create order (autopilot, one call)", "Done:" in r3 and "order" in r3.lower(), r3)
    # undo the order
    await by_name["undo_last"](None)

    # Turn 4: "assign the best welder to a new task called weld frame"
    r4 = await by_name["do_assign_task"](None, person="best welder",
                                         task_text="weld frame", autopilot=True)
    check("turn4 best welder -> weld frame", "Done:" in r4 and "assigned" in r4, r4)
    await by_name["undo_last"](None)

    # Turn 5: "delete that task" -> refusal naming the on-screen place.
    r5 = await by_name["do_change_task"](None, task_ref="that task", status="delete")
    check("turn5 delete refused (names Tasks/Orders)", "cannot" in r5.lower() and
          ("Tasks" in r5 or "Orders" in r5), r5)

    # Bonus: change priority/deadline one turn.
    a = await by_name["do_assign_task"](None, person="Ravi Kumar", task_text="CNC operation")
    r6 = await by_name["do_change_task"](None, task_ref="CNC operation", priority="URGENT",
                                         deadline="Friday")
    check("bonus change priority + deadline", "Done:" in r6, r6)
    await by_name["undo_last"](None)
    await by_name["undo_last"](None)

    fails = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(fails)}/{len(results)} PASS")
    for n in fails:
        print("  FAILED:", n)


if __name__ == "__main__":
    asyncio.run(main())

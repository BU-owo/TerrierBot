import random
import discord
from discord.ext import commands, tasks
from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from bot import TerrierBot, Context

ET = ZoneInfo("America/New_York")

LAST_DAY_CLASSES  = date(2026, 4, 30)
STUDY_PERIOD_START = date(2026, 5, 1)
STUDY_PERIOD_END   = date(2026, 5, 3)
FINALS_START       = date(2026, 5, 4)
FINALS_END         = date(2026, 5, 8)
COMMENCEMENT_START = date(2026, 5, 14)
COMMENCEMENT_END   = date(2026, 5, 17)

GENERAL_CHANNEL_ID = 1396542256445391069


def build_message(today: date) -> str | None:
    """Return a countdown message for today, or None if the semester is over."""
    if today > COMMENCEMENT_END:
        return None

    def days(n: int) -> str:
        return f"{n} day{'s' if n != 1 else ''}"

    # ── Commencement day ──────────────────────────────────────────────────────
    if today == COMMENCEMENT_END:
        return random.choice([
            "🎓 **IT'S ALL UNIVERSITY COMMENCEMENT DAY!!!** The tassel has been turned. The degree is REAL. To every graduating Terrier: you absolute legend. Go be incredible. 🐾❤️",
            "🏛️ **TODAY IS COMMENCEMENT!** Four (or more) years of chaos, caffeine, and character development — and here you are. Boston University is forever yours. Fly high! 🎓✨",
            "🎊 **COMMENCEMENT DAY HAS ARRIVED AND I AM GOING FERAL!!!** You did it!!! You actually did it!!! I never doubted you for a second (I doubted you a little during finals). 😭🐾",
            "📜 **THE DIPLOMA IS REAL. THIS IS REAL LIFE.** Someone's mom is crying on Nickerson Field RIGHT NOW. It might be me. I'm a bot. I don't have eyes. And yet. 😭🎓",
            "🐾 **TODAY WE GRADUATE.** BU said 'you are ready for the world' and the world has no idea what's coming. GO BE CHAOTIC AND BRILLIANT OUT THERE. We love you forever. 💙❤️",
            "🎺 **ALL UNIVERSITY COMMENCEMENT!!!** The saga is complete. The arc is finished. The main character has graduated. Roll credits. Post-credits scene: student loans. 🎬😭",
        ])

    # ── Commencement week ─────────────────────────────────────────────────────
    if COMMENCEMENT_START <= today < COMMENCEMENT_END:
        left = (COMMENCEMENT_END - today).days
        return random.choice([
            f"🎉 It's Commencement week! All University Commencement is in **{days(left)}**. Someone's parents are definitely lost on Comm Ave right now. 📍😭",
            f"🥂 The celebrations have begun! Big day in **{days(left)}**. Congrats to every graduating Terrier. You made it this far — finish strong! 🐾",
            f"🎓 Commencement week is HERE and the vibes are IMMACULATE. Big day in **{days(left)}**. Please hydrate. Please eat. Please do not cry on the T. (It's okay if you cry on the T.) 😭🚇",
            f"🌸 **{days(left)}** until All University Commencement. The seniors are walking around campus like they own the place. They do. They earned it. Let them have this. 🐾",
            f"🎊 We are **{days(left)}** away from the most dramatic cap-and-gown moment of the year. Tissues ready. Phone cameras charged. This is IT. 📸✨",
            f"🏛️ **{days(left)}** until Commencement. Somewhere on Comm Ave, a parent is taking 47 photos in front of Marsh Chapel RIGHT NOW. You know who you are. 📷😭",
        ])

    # ── Finals over ───────────────────────────────────────────────────────────
    if today == FINALS_END:
        return random.choice([
            "🎊 **FINALS ARE OVER!!!** You did it!!!! Whatever the grade, you SURVIVED and that deserves a full parade. 🎺🥁🎸",
            "🥳 **THE LAST FINAL IS DONE.** Close the textbook. Delete the study group chat. It is OVER. Go sleep for 14 hours. You've earned it, warrior. 🏁",
            "🚨 **FINALS ARE FINISHED. CODE RED IS CANCELLED. RETURN TO YOUR NORMAL LIVES.** Drop the flashcards. Shut the laptop. Go outside and remember what grass looks like. 🌿😭",
            "💀 **YOU SURVIVED FINALS WEEK.** Scientists are baffled. Economists are puzzled. Your mother is relieved. You are a LEGEND and I will not hear otherwise. 🐾👑",
            "🎉 **IT'S OVER IT'S OVER IT'S OVER!!!** The exams are done. The grades are what they are. That's a future-you problem. Present-you deserves to CELEBRATE. 🥂",
            "📚 **FINALS: DEFEATED.** You looked them in the eye. You studied (or didn't, no judgment). You showed up. And now it is DONE. Go eat a real meal immediately. 🍕",
            "🏆 **THE FINAL FINAL HAS BEEN FINALED.** That's not grammatically correct and I don't care. NOTHING MATTERS ANYMORE. YOU'RE FREE. 🕊️✨",
        ])

    # ── Finals in progress ────────────────────────────────────────────────────
    if FINALS_START <= today < FINALS_END:
        left = (FINALS_END - today).days
        day_num = (today - FINALS_START).days + 1
        return random.choice([
            f"📝 Finals day {day_num}. **{days(left)}** until it's all over. You've survived 100% of your hard days so far. This is just another one. ☕💪",
            f"😤 Still in the trenches. **{days(left)}** left of finals. Hydrate. Sleep. Eat something that isn't just chips. (Chips are also fine.) 🧠",
            f"⚡ Finals are happening and so are you. **{days(left)}** to go. The limit does not exist — but the end does, and it's soon. 🔥",
            f"💀 Finals day {day_num}. We are **{days(left)}** from freedom. I believe in you. The Mugar study room chairs do NOT believe in you, they are terrible, but I do. 🪑😭",
            f"🫠 Day {day_num} of finals. **{days(left)}** remaining. Your brain is a sponge and the sponge is wet and the floor is lava and somehow you're STILL going. Respect. 🧠",
            f"☕ Finals day {day_num}. **{days(left)}** left. The amount of espresso flowing through BU students right now could power a small city. You are that city. ⚡",
            f"😵 It is finals day {day_num} and we have **{days(left)}** to go. I'm not going to tell you it's easy. It's not. But you're still here, and that means everything. 🐾",
            f"🔥 Finals day {day_num}. **{days(left)}** days until it ends. Somewhere a professor is writing 'this is a challenging exam' in an email and feeling ZERO remorse. You've got this anyway. 😤",
            f"💪 If stress burned calories, every Terrier on this campus would be in peak athletic condition right now. Finals day {day_num}. **{days(left)}** to go. Channeling it all into the exam. 🏅",
            f"☕ Shoutout to caffeine for single-handedly holding this university together. Day {day_num} of finals. **{days(left)}** left. Without it, the collective GPA of BU collapses. We don't talk about that. 🙏",
            f"📝 Finals day {day_num}. **{days(left)}** left. Reminder: you are not failing. You are *academically misunderstood*. The exam simply could not comprehend your genius. 🧠✨",
            f"😤 Finals day {day_num}. **{days(left)}** left. If you pass this course it will be out of pure spite and sheer force of will — not because you understood the material. That still counts. 💪",
            f"🙈 Finals day {day_num}. **{days(left)}** left. Grading philosophy that has never failed: if you simply do not check your grades, they cannot hurt you. Ignorance is a coping strategy. 🙈",
            f"🥤 Finals day {day_num}. **{days(left)}** until it's over. Sleep schedule: destroyed. Energy drink count: deeply concerning. Problems solved by caffeine alone: all of them, allegedly. 💀",
            f"😵 It is finals day {day_num} and **{days(left)}** remain. It's 3am somewhere on this campus. Someone just reread the same paragraph eight times. That someone has my full respect and my deepest condolences. 🕯️",
        ])

    # ── Finals start today ────────────────────────────────────────────────────
    if today == FINALS_START:
        return random.choice([
            "📝 **FINALS HAVE BEGUN.** The vibe is: panic, caffeine, and questionable life choices. You have trained for this. (Right? ...Right?) 😅",
            "😱 **IT'S FINALS SEASON, BABY.** May your notes be readable, your professors merciful, and your WiFi stable. Go get 'em. 🐾",
            "☕ **FINALS START TODAY.** The library is now your home. Snacks are your only friends. You are a machine. A very stressed, very capable machine. YOU GOT THIS.",
            "🚨 **FINALS HAVE OFFICIALLY STARTED. THIS IS NOT A DRILL. I REPEAT, THIS IS NOT A DRILL.** Deep breath. You have done hard things before. You will do this hard thing. Go. 💪",
            "😤 **THE EXAM GAMES HAVE BEGUN.** May the odds be ever in your favor and may your professor have accidentally made the test too easy. Probably not. But maybe. 🎯",
            "📖 **TODAY FINALS BEGIN.** Somewhere a student is realizing they studied the wrong chapters. That student is not you. (Please let that student not be you.) 😭🐾",
            "🫡 **FINALS DAY ONE IS HERE.** This is the part of the movie where the training montage pays off. Cue the music. You are the protagonist. GO. 🎬🔥",
            "🧠 **IT IS FINALS O'CLOCK.** The semester has been building to this exact moment. You have notes (hopefully). You have sleep (less hopefully). You have HEART. That's enough. 💙",
            "😰 **FINALS WEEK HAS BEGUN.** Or as I like to call it: my final week. One of us will not make it out the same. (You will. You got this. Probably. Go ace it.) 💀🐾",
        ])

    # ── Study period ──────────────────────────────────────────────────────────
    if STUDY_PERIOD_START <= today <= STUDY_PERIOD_END:
        left = (FINALS_START - today).days
        day_num = (today - STUDY_PERIOD_START).days + 1
        return random.choice([
            f"📖 Study period day {day_num}. Finals in **{days(left)}**. This is your villain-origin-story study arc. Make it legendary. 🖤📚",
            f"😬 Study period is upon us. **{days(left)}** until finals begin. The library is open. Your fate is unwritten. Let's keep it that way. ✍️",
            f"☕ **{days(left)}** until finals. The semester isn't dead yet — and neither are you. Close TikTok. Open your notes. Let's go. 🔥",
            f"🕯️ Study period day {day_num}. **{days(left)}** until finals. The vibes are somber. The flashcards are many. The snacks are the only thing keeping us going. 🍕📚",
            f"😤 Day {day_num} of study period. **{days(left)}** until the exams begin. This is the calm before the storm. USE IT. Please. I'm begging. 🌩️",
            f"📚 Study period, day {day_num}. **{days(left)}** days of freedom remain. Somewhere a student just made a color-coded study schedule and immediately felt better about everything. Be that student. 🖍️",
            f"🫠 Study period day {day_num}. Finals in **{days(left)}**. The Mugar library is operating at full chaos capacity. Godspeed to everyone who needs a desk. 🏃‍♂️💨",
            f"⏳ **{days(left)}** until finals start and the study period is NOT playing around. Review your notes. Call your mom. Eat a vegetable. Not necessarily in that order. 🥦",
            f"🫙 Study period day {day_num}. Finals in **{days(left)}**. Did you spend the semester procrastinating? No. You were *marinating*. Slow-cooking your knowledge. It develops flavor under pressure. 🍖",
            f"🖥️ Study period day {day_num}. Finals in **{days(left)}**. Current study strategy: 17 browser tabs open, one of them is actually relevant, trusting the universe for the rest. Perfectly normal. 🌌",
            f"😔 Study period day {day_num}. Finals in **{days(left)}**. You don't need a study break. You need a complete life restructure. But a snack and a glass of water will do for now. 🍕",
        ])

    # ── Last day of classes ───────────────────────────────────────────────────
    if today == LAST_DAY_CLASSES:
        return random.choice([
            "🎉 **TODAY IS THE LAST DAY OF CLASSES!!!** Go survive that final lecture and weep tears of joy. Study period starts tomorrow, but TODAY is a victory lap. 🏃‍♂️💨",
            "🔔 **LAST. DAY. OF. CLASSES.** Pour one out for every 8am you survived this semester. You have come SO far. 🫡",
            "📚 **IT'S THE LAST DAY OF CLASSES!** Somewhere a professor is squeezing in 'this will definitely be on the final.' You've got this. Probably.",
            "🚨 **THE FINAL LECTURE OF THE SEMESTER IS TODAY AND I AM NOT OKAY ABOUT IT!!!** The whiteboards have said their last. The syllabi are spent. Go forth and attend. 😭📓",
            "🎓 **LAST DAY OF CLASSES. THE SEMESTER IS BREATHING ITS FINAL BREATH.** Attend your classes. Say goodbye to your professors (or don't, no judgment). This is history. 🏛️",
            "😭 **IT'S THE LAST DAY OF CLASSES!!!** Some of you are crying. Some of you are numb. Some of you checked out three weeks ago. All valid. All understood. LAST DAY BABY. 🐾",
            "🏁 **LAST DAY OF CLASSES HAS ARRIVED.** The semester that started with hope, continued with chaos, and ends with vibes. Study period begins tomorrow. Mourn today. 🕯️",
            "📣 **THE LAST CLASS OF THE SEMESTER IS HAPPENING TODAY!!!** Absorb whatever is being said. Take notes. Or stare into the middle distance. Both are valid final-day activities. 🌀",
        ])

    # ── Counting down to last day of classes ──────────────────────────────────
    left = (LAST_DAY_CLASSES - today).days
    if left <= 0:
        return None  # shouldn't happen, safety net

    weekday = today.weekday()  # 0=Mon … 6=Sun
    is_weekend = weekday >= 5

    if is_weekend:
        day_name = "Saturday" if weekday == 5 else "Sunday"
        return random.choice([
            f"🌅 Happy {day_name}! No classes today, but the clock is still ticking. **{days(left)}** until the last day of classes. Rest up — you'll need it. 😴",
            f"🛌 Weekend mode activated! **{days(left)}** until classes wrap up. Touch some grass, eat a real meal, and mentally prepare. 🌿",
            f"☀️ It's {day_name}, the one day the semester can't touch you. **{days(left)}** left of classes. Enjoy the peace while it lasts. 🕊️",
            f"😴 It's {day_name} and zero classes are happening and that's the most beautiful sentence in the English language. **{days(left)}** until the last day of classes. Cherish this. 🐾",
            f"🛋️ Happy {day_name}! **{days(left)}** left until classes end. You are legally required to do nothing productive right now. Rest is resistance. Go lie down. 🫡",
            f"🌿 It's {day_name}. The professors cannot reach you here. **{days(left)}** until the last day of classes. This is your safe space. Heal. Recover. Eat brunch like it means something. 🍳",
            f"☕ {day_name} energy: cozy, unbothered, thriving. **{days(left)}** until the last day of classes. Whatever you're doing today, you deserve it. 🌸",
        ])

    if left == 1:
        return random.choice([
            "🫡 **1 day left until the last day of classes.** One final push. That light at the end of the tunnel? That's not a train — that's FREEDOM. 🚄💨",
            "😤 **TOMORROW is the last day of classes.** ONE. MORE. DAY. You have come so far. Don't blow it now (jk, you're absolutely fine). 🐾",
            "🚨 **1 DAY. ONE SINGLE DAY.** The last day of classes is TOMORROW. We have been through SO much together. Finish strong, you incredible human. 💙",
            "😭 **TOMORROW IS THE LAST DAY OF CLASSES AND I CANNOT HANDLE IT.** One more day. Just one. You have survived every single day of this semester and you will survive one more. 🐾",
            "🔥 **24 HOURS. THAT'S ALL.** One more day of classes and then it's study period and then it's finals and then... FREEDOM. Okay that got dark fast. YOU GOT THIS. 💪",
        ])

    if left <= 3:
        return random.choice([
            f"🔥 **{days(left)}** until the last day of classes. We are SO close. Can you feel it?? That's the smell of almost-freedom. 👃✨",
            f"😤 **{days(left)}** left. The finish line is RIGHT there. Don't you dare give up now. 💪🐾",
            f"🏃 **{days(left)}** until classes end. This is the sprint portion of the semester. Your legs hurt. Your brain hurts. KEEP GOING. The tape is right there. 🎽",
            f"😤 **{days(left)}** days of classes left. We are in the ENDGAME now. Everything before this was the warm-up. Give it everything you've got. 🔥🐾",
            f"⚡ **{days(left)}** until the last day of classes. You can literally see the finish line from here. Don't you DARE walk when you should be sprinting. GO. 🏁",
        ])

    if left <= 7:
        return random.choice([
            f"📅 **{days(left)}** until the last day of classes. Less than a week. You're basically already done. (You're not. Go to class.) 😅",
            f"⏳ **{days(left)}** until classes end. The semester is gasping its final breath. Hold on just a little longer. 🐾",
            f"🗓️ Only **{days(left)}** of classes left! Finals are lurking after that, but let's celebrate the small wins. Almost there! 🎉",
            f"👀 **{days(left)}** until the last day of classes. We are dangerously close to the end. The semester can smell your fear. Do not let it win. 😤",
            f"🎯 **{days(left)}** days. That's it. The end of the semester is not a concept anymore — it is a scheduled event on the calendar and it is COMING. 📅🔥",
            f"😤 **{days(left)}** until classes wrap up. Less than a week. The professors are still assigning things and we will not be discussing how that makes me feel. 🙂",
            f"⏰ **{days(left)}** days until the last class. The semester timer is blinking red. Protect your attendance record. Show up. You've come too far not to. 🐾",
            f"📖 **{days(left)}** until the last day of classes. The syllabus listed 'optional readings.' You took that personally. You skipped every single one. Zero regrets. Truly. 🫡",
            f"🤺 **{days(left)}** left. At what point does 'academic weapon' tip over into 'academic liability'? We're asking the important questions this close to the end. 🗡️",
        ])

    return random.choice([
        f"📆 **{days(left)}** until the last day of classes. The end is visible on the horizon. Keep pushing! 🌅",
        f"🐾 Terrier check-in! **{days(left)}** until classes wrap up. Boston University believes in you — and so do we. ❤️",
        f"⏰ **{days(left)}** of classes remaining. Every lecture from here is pure character development. 🧠",
        f"📚 Countdown to freedom: **{days(left)}** left. The grind continues, but so do you. 💪",
        f"🗓️ **{days(left)}** until the last day of classes. You know what you need to do. Go do it. We believe in you aggressively. 💙🐾",
        f"😤 **{days(left)}** days of class left. Not few. Not many. Just **{days(left)}**. Each one is a step closer to the end. Take the step. 🚶",
        f"📣 TerrierBot reporting in: **{days(left)}** until classes end. The semester is still alive and so are you. Do not give up now. I will be watching. 👀",
        f"☕ **{days(left)}** until the last day of classes. Some of you are thriving. Some of you are surviving. Both count. Keep going. 🐾",
        f"🌅 **{days(left)}** days left of class. That's {left * 24} hours. That's {left * 1440} minutes. That's a lot of minutes. Don't think about it. Just go to class. 😅",
        f"🔥 **{days(left)}** left until the last day of classes. The semester is not going to destroy you. You are going to DESTROY THE SEMESTER. Get it. 💪",
        f"🚀 T-minus **{days(left)}** until we collectively gaslight ourselves into believing we retained any of this information. The experiment is ongoing. Science. 🧪",
        f"🤔 **{days(left)}** until the last day of classes. Real question: at what point does 'academic weapon' become 'academic liability'? Asking for a friend. The friend is all of us. 🗡️",
        f"👥 **{days(left)}** until the last day of classes. Fun semester reflection: group projects are just social experiments with a GPA attached. Results: inconclusive. Relationships: strained. 🔬",
        f"💼 **{days(left)}** until classes end. Work ethic status: strong, powerful, present in spirit — just not fully activated at this exact moment. It'll kick in. Any minute now. ⏱️",
        f"🎓 Higher education. It really is so… *higher*. **{days(left)}** until the last day of classes. Soak in every moment of this beautiful, chaotic experience. 🤌",
    ])


class EndCog(commands.Cog, name="End"):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        self.announcement_task.start()
        print("End Cog Ready")

    def cog_unload(self):
        self.announcement_task.cancel()

    @tasks.loop(time=[time(10, 0, tzinfo=ET), time(16, 0, tzinfo=ET)])
    async def announcement_task(self):
        today = datetime.now(ET).date()
        msg = build_message(today)
        if msg is None:
            self.announcement_task.cancel()
            return
        channel = self.bot.get_channel(GENERAL_CHANNEL_ID)
        if isinstance(channel, discord.TextChannel):
            await channel.send(msg)

    @announcement_task.before_loop
    async def before_announcement(self):
        await self.bot.wait_until_ready()

    @commands.command()
    async def end(self, ctx: Context):
        """How many days until the semester ends?"""
        today = datetime.now(ET).date()
        msg = build_message(today)
        if msg is None:
            await ctx.send("🎓 The semester is over! Congratulations, Terriers! Go live your beautiful life. 🐾❤️")
            return
        await ctx.send(msg)


async def setup(bot: TerrierBot):
    await bot.add_cog(EndCog(bot))

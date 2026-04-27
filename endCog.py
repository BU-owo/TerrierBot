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
            "🎓 **IT'S ALL UNIVERSITY COMMENCEMENT DAY!!!** Good job gamers!",
            "🏛️ **TODAY IS COMMENCEMENT!** Time to go stand in the field and feel hot :) because it is summer",
            "🎊 **COMMENCEMENT DAY HAS ARRIVED AND I AM GOING FERAL!!!** ARF ARF WOOF BARK GRRRRRRRRRRRRR MEOW MEOW ARF ARF BARK GROWL ARRRRGGGG WOOF",
            "🐾 **TODAY WE GRADUATE.** Unless youre a silly freshman! Because they do not graduate yet :)",
            "🎺 **ALL UNIVERSITY COMMENCEMENT!!!** GO GET A JOB now haha members of the workforce XD",
        ])

    # ── Commencement week ─────────────────────────────────────────────────────
    if COMMENCEMENT_START <= today < COMMENCEMENT_END:
        left = (COMMENCEMENT_END - today).days
        return random.choice([
            f"🎉 It's Commencement week! All University Commencement is in **{days(left)}**. You should probably take photos or soomething",
            f"🥂 The celebrations have begun! Big day in **{days(left)}**. Congrats to all future unemployed homeless people heheh  🐾",
            f"🎓 Commencement week is HERE. Big day in **{days(left)}**. You should drink. Water? Choo choo 😭🚇",
            f"🌸 **{days(left)}** until All University Commencement. Are you gonna go?. 🐾",
            f"🎊 We are **{days(left)}** away from the big graduation ceremony YIPPEE 📸✨",
            f"🏛️ **{days(left)}** until Commencement. You should take photos and stuff to remember the week or smyn? 📷😭",
        ])

    # ── Finals over ───────────────────────────────────────────────────────────
    if today == FINALS_END:
        return random.choice([
            "🎊 **FINALS ARE OVER!!!** You did it!!!! I hope you passed!!!!!!!!!!! 🎺🥁🎸",
            "🥳 **THE LAST FINAL IS DONE.** You should probably burn all of your notes heheheh fire emoji ahahahaha. 🏁",
            "🚨 **FINALS ARE FINISHED. RETURN TO YOUR NORMAL LIVES.** HAHAH IT SAYS NORMAL. Like Kass? fonny 🌿😭",
            "💀 **YOU SURVIVED FINALS WEEK.** Unless you are dead now. In which case, you are not alive 🐾👑",
            "🎉 **IT'S OVER IT'S OVER IT'S OVER!!!** JUMP INTO THE CHARLES RIVER NOW. 🥂",
            "📚 **FINALS: DEFEATED.**  Good job gamers🍕",
            "🏆 **THE FINAL FINAL HAS BEEN EATEN.**. nom nom nom nom nom 🕊️✨",
        ])

    # ── Finals in progress ────────────────────────────────────────────────────
    if FINALS_START <= today < FINALS_END:
        left = (FINALS_END - today).days
        day_num = (today - FINALS_START).days + 1
        return random.choice([
            f"📝 Finals day {day_num}. **{days(left)}** until it's all over. Are you alive?. ☕💪",
            f"😤 **{days(left)}** left of finals.drink alochol 🧠",
            f"⚡ Finals are happening and so are you. **{days(left)}** to go. The AI wrote this but i leaves it cuz funny. 🔥",
            f"💀 Finals day {day_num}. We are **{days(left)}** from done. Lock in bitch. 🪑😭",
            f"🫠 Day {day_num} of finals. **{days(left)}** remaining. Your brain is a sponge and the sponge is wet and the floor is lava. Claude wrote that. 🧠",
            f"☕ Finals day {day_num}. **{days(left)}** left. Inject caffeine like heroin ⚡",
            f"😵 It is finals day {day_num} and we have **{days(left)}** to go. You gonna survive bruv? 🐾",
            f"🔥 Finals day {day_num}. **{days(left)}** days until it ends. 102838123 days until profs finish grading the exams. 😤",
            f"☕ Shoutout to celsius. Day {day_num} of finals. **{days(left)}** left. Mmmmm celsius 🙏",
            f"📝 Finals day {day_num}. **{days(left)}** left. Reminder: you are not failing. Gosh youre a genius. 🧠✨",
            f"😤 Finals day {day_num}. **{days(left)}** left. Do you think youre gonna pass? 💪",
            f"🙈 Finals day {day_num}. **{days(left)}** left. You should drop your class that you hate. 🙈",
            f"🥤 Finals day {day_num}. **{days(left)}** until it's over. Don't pull all nighters. 💀",
            f"😵 It is finals day {day_num} and **{days(left)}** remain. Don't do drugs. 🕯️",
        ])

    # ── Finals start today ────────────────────────────────────────────────────
    if today == FINALS_START:
        return random.choice([
            "📝 **FINALS HAVE BEGUN.** LOCK THE FUCK IN 😅",
            "😱 **IT'S FINALS SEASON, BABY.** you got dis gumdrops!!!1 🐾",
            "☕ **FINALS START TODAY.** suffering time YIPPEEEEEEEEEE",
        ])

    # ── Study period ──────────────────────────────────────────────────────────
    if STUDY_PERIOD_START <= today <= STUDY_PERIOD_END:
        left = (FINALS_START - today).days
        day_num = (today - STUDY_PERIOD_START).days + 1
        return random.choice([
            f"📖 Study period day {day_num}. Finals in **{days(left)}**. Lock in 🖤📚",
            f"😬 Study period is upon us. **{days(left)}** until finals begin. The library is open. Your fate is unwritten. Let's keep it that way. ✍️",
            f"☕ **{days(left)}** until finals. STOP. 🔥",
            f"🕯️ Study period day {day_num}. **{days(left)}** until finals. Be sober. Eat. 🍕📚",
        ])

    # ── Last day of classes ───────────────────────────────────────────────────
    if today == LAST_DAY_CLASSES:
        return random.choice([
            "🎉 **TODAY IS THE LAST DAY OF CLASSES!!!** TIME to LOCK IN for finals!!!!!!! 🏃‍♂️💨",
            "🔔 **LAST. DAY. OF. CLASSES.** Consume an alcoholic beverage if legal. 🫡",
            "📚 **IT'S THE LAST DAY OF CLASSES!** YIPPE YIPPEEE YYIPPEEEEEEEEEE",
            "😭 **IT'S THE LAST DAY OF CLASSES!!!** I AM NUMB INSIDE AHA. 🐾",
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
            f"🌅 Happy {day_name}! No classes today, but you still gotta lock in. **{days(left)}** until the last day of classes. 😴",
            f"🛌 Weekend time! **{days(left)}** until classes end. Touch some grass. 🌿",
            f"☀️ It's {day_name}. **{days(left)}** left of classes. WWAHHHHHHHHHHHHH. 🕊️",
            f"😴 It's {day_name} and that means no class. **{days(left)}** until the last day of classes. Thank rhett. 🐾",
        ])

    if left == 1:
        return random.choice([
            "🫡 **1 day left until the last day of classes.** Please please please please hurry up. 🚄💨",
            "😤 **TOMORROW is the last day of classes.** ONE. MORE. DAY. I think you can survive this. 🐾",
            "🚨 **1 DAY.** The last day of classes is TOMORROW. ALMOST THERE LOSERSSSSSSSSSSS. 💙",
            "😭 **TOMORROW IS THE LAST DAY OF CLASSES RAHHHHHHHH.** just gonna survive 1 more! 🐾",
            "🔥 **24 HOURS. THAT'S ALL.** LOCK IN BITCHES IT IS ALMOST OVER. 💪",
        ])

    if left <= 3:
        return random.choice([
            f"🔥 **{days(left)}** until the last day of classes. We are SO close, just like my ex wife. 👃✨",
            f"😤 **{days(left)}** left. Unlike your girlfriend, the semester is gonna finish. 💪🐾",
            f"🏃 **{days(left)}** until classes end. GO GO GO GO GO GO GO GO. 🎽",
            f"😤 **{days(left)}** days of classes left. Almost there nerds!!!!! 🔥🐾",
            f"⚡ **{days(left)}** until the last day of classes. you got this gumdrop! 🏁",
        ])

    if left <= 7:
        return random.choice([
            f"📅 **{days(left)}** until the last day of classes. Less than a week. Skip the rest of your classes heehee 😅",
            f"⏳ **{days(left)}** until classes end. Hold on a bit longer.... 🐾",
            f"🗓️ Only **{days(left)}** of classes left! Don't forget we have finals after YIPPEE! 🎉",
            f"👀 **{days(left)}** until the last day of classes. It REEKS in here. 😤",
            f"🎯 **{days(left)}** days. I CAN FEEL IT COMOING HAHAHAHAHAHAA. 📅🔥",
            f"😤 **{days(left)}** until classes wrap up. It's cwazy bro. 🙂",
            f"⏰ **{days(left)}** days until the last class. you hoes have GOT THIS. 🐾",
            f"📖 **{days(left)}** until the last day of classes. SKIP THE READINGS AND TAKE A NAP. 🫡",
            f"🤺 **{days(left)}** left. Youre an academic eweapon my GOAT. 🗡️",
        ])

    return random.choice([
        f"📆 **{days(left)}** until the last day of classes. ALLLLLLLLMOST THEREEEEEEEE 🌅",
        f"🐾 Terrier check-in! **{days(left)}** until classes wrap up. You got dis! ❤️",
        f"⏰ **{days(left)}** of classes remaining. GRIND BITCH, GRIND! 🧠",
        f"🗓️ **{days(left)}** until the last day of classes. LOCK IN. 💙🐾",
        f"☕ **{days(left)}** until the last day of classes. YOU WILL SRURVIVE TRUST!!!!! 🐾",
        f"🌅 **{days(left)}** days left of class. That's {left * 24} hours. That's {left * 1440} minutes. Guh. 😅",
        f"🔥 **{days(left)}** left until the last day of classes. DESTROY THIS BITCH. 💪",
        f"🚀 T-minus **{days(left)}** until we forget everything we learned yay! 🧪",
        f"💼 **{days(left)}** until classes end. How are ya feeling? ⏱️",
    ])


def build_scheduled_message(today: date) -> str | None:
    """Return a plain informational message for scheduled announcements."""
    if today > COMMENCEMENT_END:
        return None

    def days(n: int) -> str:
        return f"{n} day{'s' if n != 1 else ''}"

    if today == COMMENCEMENT_END:
        return "🎓 **Today is All University Commencement!** Congratulations to all graduating Terriers!!!!!!!!!!!! 🐾❤️"

    if COMMENCEMENT_START <= today < COMMENCEMENT_END:
        left = (COMMENCEMENT_END - today).days
        return f"🎓 **Commencement week!** All University Commencement is in **{days(left)}**. Congratulations to all graduating Terriers! Y'all are awesom!!! 🐾"

    if today == FINALS_END:
        return "✅ **Finals are over!** Great work this semester, gamers! 🐾"

    if FINALS_START <= today < FINALS_END:
        left = (FINALS_END - today).days
        day_num = (today - FINALS_START).days + 1
        return f"📝 **Finals — Day {day_num}.** **{days(left)}** remaining until finals end. Good luck babyyyyyyy! 🐾"

    if today == FINALS_START:
        return f"📝 **Finals begin today!** They run through **{FINALS_END.strftime('%B %d')}**. You've got this. DESTROY those exams. 🐾"

    if STUDY_PERIOD_START <= today <= STUDY_PERIOD_END:
        left = (FINALS_START - today).days
        day_num = (today - STUDY_PERIOD_START).days + 1
        return f"📖 **Study Period — Day {day_num}.** Finals begin in **{days(left)}** on {FINALS_START.strftime('%B %d')}. LOCK IN! 🐾"

    if today == LAST_DAY_CLASSES:
        return "🎉 **Today is the last day of classes!** Study period begins tomorrow. 🐾"

    left = (LAST_DAY_CLASSES - today).days
    if left <= 0:
        return None

    return f"📅 **{days(left)}** until the last day of classes ({LAST_DAY_CLASSES.strftime('%B %d')}). 🐾"


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
        msg = build_scheduled_message(today)
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
            await ctx.send("🎓 The semester is over! Congratulations, Terriers! Go live your life. 🐾❤️")
            return
        await ctx.send(msg)


async def setup(bot: TerrierBot):
    await bot.add_cog(EndCog(bot))

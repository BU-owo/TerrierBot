import random
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from bot import TerrierBot, Context

ET = ZoneInfo("America/New_York")

# ── Key dates (Fall 2026) ───────────────────────────────────────────────────
NEW_STUDENT_MOVEIN_START = date(2026, 8, 24)   # New student move-in (orientation)
NEW_STUDENT_MOVEIN_END   = date(2026, 8, 25)
ORIENTATION_START        = date(2026, 8, 26)   # Orientation programming & events
ORIENTATION_END          = date(2026, 9, 1)
CONTINUING_MOVEIN_START  = date(2026, 8, 28)   # Continuing student move-in (overlaps orientation)
CONTINUING_MOVEIN_END    = date(2026, 8, 31)
MATRICULATION            = date(2026, 9, 1)    # Same day as end of orientation
CLASSES_BEGIN            = date(2026, 9, 2)    # First day of classes

GENERAL_CHANNEL_ID = 1396542256445391069  # TODO: confirm/replace channel id


def build_message(today: date) -> str | None:
    """Return a silly countdown message for today, or None once classes have started."""
    if today > CLASSES_BEGIN:
        return None

    def days(n: int) -> str:
        return f"{n} day{'s' if n != 1 else ''}"

    # ── Classes begin (1 day → 4 msgs) ─────────────────────────────────────
    if today == CLASSES_BEGIN:
        return random.choice([
            "📚 **CLASSES HAVE BEGUN!!!** wake up and get to class bro!",
            "🎒 **TODAY IS DAY ONE.** like a hundred and smtn days to go WOO HOOOOOO",
            "🐾 **IT'S HAPPENING. CLASSES START TODAY.** you got this!!!!!!",
            "🔥 **FIRST DAY OF CLASSES BABYYYY.** go pretend you did the reading yahoo!!",
        ])

    # ── Matriculation day (1 day → 4 msgs) ──────────────────────────────────
    if today == MATRICULATION:
        return random.choice([
            "🎓 **TODAY IS MATRICULATION!!!** good job matriculants!",
            "🐾 **WELCOME TO THE BOSTON UNIVERSITY OFFICIALLY.** now use those student discounts!",
            "🏛️ **MATRICULATION DAY.** pump and circumcision!",
            "🎺 **YOU ARE NOW OFFICIALLY MATRICULATED.** pls don't matriculate in your room with your roommate there!",
        ])

    # ── Orientation programming (Aug 26–31 → 6 days → 24 msgs) ──────────────
    if ORIENTATION_START <= today < ORIENTATION_END:
        left = (CLASSES_BEGIN - today).days
        day_num = (today - ORIENTATION_START).days + 1
        return random.choice([
            f"🎉 Orientation day {day_num}. Classes start in **{days(left)}**. hope youre orienting well!",
            f"🐾 **{days(left)}** until classes. Orientation is happening!! make friends you will never talk to again yaya!",
            f"🧭 Orientation day {day_num}. **{days(left)}** left. waow i love icebreakers yay!",
            f"🥤 Day {day_num} of orientation. **{days(left)}** until class starts. drink the free lemonade they give you!",
            f"🎪 Orientation day {day_num}. **{days(left)}** to go. Make up your fun fact for the icebreaker game, make people think you are quirky!",
            f"🐾 **{days(left)}** until classes. Day {day_num} of orientation. get the instagrams of the people around you",
            f"📛 Day {day_num}, orientation. **{days(left)}** left. Invite people to discord dot gg slash bostonuniversity",
            f"🎶 Orientation day {day_num}. **{days(left)}** until classes. clap clap clap clap round of apawse",
            f"🧃 Day {day_num} of orientation. **{days(left)}** to go. drink alcohol",
            f"🏫 Orientation day {day_num}. **{days(left)}** left. stealing from cityco is punishable by expulsion",
            f"🐾 **{days(left)}** until classes. Orientation day {day_num}. I like your lanyard you look very cute in it uwu!",
            f"📸 Day {day_num} of orientation. **{days(left)}** left. make new lifelong fwends!",
            f"🎯 Orientation day {day_num}. **{days(left)}** to go. You are so brave good job!",
            f"🗺️ Day {day_num}, orientation. **{days(left)}** until classes. Google Maps",
            f"🐾 **{days(left)}** left. Orientation day {day_num}. become enemies with your roommate",
            f"🎈 Orientation day {day_num}. **{days(left)}** to go. aquire free shit everywhere",
            f"📚 Day {day_num} of orientation. **{days(left)}** unti classes. become lovers with your roommate",
            f"🐾 **{days(left)}** left. Orientation day {day_num}. dont lose your BU ID silly",
            f"🎤 Orientation day {day_num}. **{days(left)}** to go. Ask your orientation leader a difficult question",
            f"🚶 Day {day_num}, orientation. **{days(left)}** until classes. do a practice walk of campus!!!!!",
            f"🐾 **{days(left)}** left. Orientation day {day_num}. eat something green at least once this week!",
            f"🎓 Orientation day {day_num}. **{days(left)}** to go. Memorize your BU ID number! Paste it in this chat as proof!",
            f"🧢 Day {day_num} of orientation. **{days(left)}** until classes. wear the free shirt they gave you, you look adoworable!",
            f"🐾 **{days(left)}** left. Orientation day {day_num}. almost done, hang in there puppy!!",
        ])

    # ── New student move-in (Aug 24–25 → 2 days → 8 msgs) ───────────────────
    if NEW_STUDENT_MOVEIN_START <= today <= NEW_STUDENT_MOVEIN_END:
        left = (CLASSES_BEGIN - today).days
        return random.choice([
            f"📦 **MOVE-IN DAY FOR NEW STUDENTS!** Classes in **{days(left)}**. CLEAN YOUR DESK AND BED THERE MIGHT BE SUSPICIOUS FLUIDS ON THEM",
            f"🐾 New Terriers moving in today!! **{days(left)}** until classes. Dont call your new roommies slurs or mean things!",
            f"📦 **WELCOME NEW TERRIERS!** **{days(left)}** until classes. put dead rodents in the microfridge",
            f"🧳 Move-in day for new students. **{days(left)}** left. say hi to your RA!",
            f"📦 New students, its move-in day!! **{days(left)}** until classes. keep your door open when youre in to make fwends!!!!",
            f"🐾 **{days(left)}** left. Welcome to campus, new Terriers! growl arf arf arf grrrrrr",
            f"📦 Move-in day! **{days(left)}** until classes. hydrate.",
            f"🎒 New Terriers arriving today. **{days(left)}** left. dont lose your key or you have to payyyyy",
        ])

    # ── Continuing student move-in (Aug 28–31 → 4 days → 16 msgs) ───────────
    if CONTINUING_MOVEIN_START <= today <= CONTINUING_MOVEIN_END:
        left = (CLASSES_BEGIN - today).days
        return random.choice([
            f"📦 Continuing students moving in today. **{days(left)}** until classes. welcome back to campus!",
            f"🐾 Welcome back!! **{days(left)}** left until classes start. dont forget to say hi to your thub fwends!!",
            f"📦 Move-in for returning Terriers. **{days(left)}** until classes. go find out if your fave restaurant still tasty",
            f"🐾 **{days(left)}** left. Welcome back! reconnect with your campus freidns!!!!!",
            f"📦 Returning students, move-in day. **{days(left)}** until classes. hey im walkin here!",
            f"🐾 Welcome back to campus! **{days(left)}** left. clean your bed",
            f"📦 Continuing student move-in. **{days(left)}** until classes. hide your valuables from your thieving roommie",
            f"🐾 **{days(left)}** left until classes. Welcome back!! go say hi to a owo!",
            f"📦 Move-in day for returners. **{days(left)}** until classes. be nice to ur ra",
            f"🐾 Welcome back Terriers! **{days(left)}** left. get ready for classesssssssss",
            f"📦 Continuing students, its move-in day. **{days(left)}** until classes. dont buy textbooks!!!!!!",
            f"🐾 **{days(left)}** left. Welcome back! follow terrier hub on instagram!",
            f"📦 Move-in for returners. **{days(left)}** until classes. find a campus squirrel and send a picture in this channel",
            f"🐾 Welcome back!! **{days(left)}** left. be nice to the dining hall and facilities staff",
            f"📦 Continuing student move-in day. **{days(left)}** until classes. START SEARCHING FOR FALL2026 HUZZ!",
            f"🐾 **{days(left)}** left. Welcome back Terriers! dont start studying yet tho",
        ])

    # ── General pre-move-in countdown (Aug 11–23 → 13 days → 52 msgs) ───────
    left = (CLASSES_BEGIN - today).days
    return random.choice([
        f"⏳ **{days(left)}** until classes begin. enjoy the freedom while it lasts!",
        f"🐾 **{days(left)}** left of summer. enjoy it while it lasts babyyyyy",
        f"🎒 **{days(left)}** until Fall 2026 kicks off. get ready to learn knowledge!",
        f"☀️ **{days(left)}** of summer left. go touch grass!",
        f"🐾 **{days(left)}** until classes. DO NOT BUY TEXTBOOKS",
        f"🎓 **{days(left)}** left until Fall 2026. emotionally prepare",
        f"🌅 **{days(left)}** until classes begin. fix your fucked up sleep schedule brorito",
        f"🐾 **{days(left)}** left of summer freedom. taco salad tasty",
        f"📚 **{days(left)}** until classes start. pirate your textbooks!",
        f"🎒 **{days(left)}** left. dont pack yet",
        f"🐾 **{days(left)}** until Fall 2026. skoo time soon",
        f"🌊 **{days(left)}** of summer remaining. go do something fun like video game or outside",
        f"🐾 **{days(left)}** left until classes. spend more time on terrier hub!",
        f"🎓 **{days(left)}** until Fall semester. get rested up!",
        f"🍂 **{days(left)}** until classes start. send a flirtatious text to your roommate",
        f"🐾 **{days(left)}** left of summer. do you know where your classes are?",
        f"📖 **{days(left)}** until classes begin. ignore emails from professors....",
        f"🎒 **{days(left)}** left. cant wait for the disaster known as fenway target....",
        f"🐾 **{days(left)}** until Fall 2026 begins. are you taking an 8am?",
        f"☕ **{days(left)}** until classes start. drink alcohol",
        f"🌞 **{days(left)}** of summer left. go outside",
        f"🐾 **{days(left)}** until classes. hug your pet if you have one!",
        f"🎓 **{days(left)}** left until Fall 2026. what is the song of your summer?",
        f"📦 **{days(left)}** until classes begin. RUBY CHAN! HAIIIIIII NANI HA SUKI? CHOCOMINTO YORI GA ANATA!",
        f"🐾 **{days(left)}** left of summer. watch a whole season of something",
        f"🎒 **{days(left)}** until Fall semester starts. it too hot out",
        f"🌻 **{days(left)}** left of summer. buy things with money. you deserve a gift.",
        f"🐾 **{days(left)}** until classes. go to bed",
        f"📚 **{days(left)}** until Fall 2026 begins. be brave, soldier....",
        f"🎓 **{days(left)}** left. skool soon",
        f"🐾 **{days(left)}** until classes start. are you excited for dining hall food?",
        f"🌤️ **{days(left)}** of summer remaining. boston is gonna be snowy this year trust",
        f"🐾 **{days(left)}** left until Fall 2026. make sure to pak your passpowort",
        f"🎒 **{days(left)}** until classes begin. enjoy the privacy before getting to campus with your weird invasive roommate. Ping your roommate below:",
        f"📖 **{days(left)}** left of summer. read yuri, not textbooks",
        f"🐾 **{days(left)}** until Fall semester starts. practice flirting.",
        f"🎓 **{days(left)}** left. she sylla on my bus til I quiz.",
        f"🌙 **{days(left)}** until classes begin. your mum",
        f"🐾 **{days(left)}** left of summer. how ar eyou feeling????!",
        f"📦 **{days(left)}** until Fall 2026 starts. pack your towels?",
        f"🎒 **{days(left)}** left. exciting!!!!!!!",
        f"🐾 **{days(left)}** until classes begin. enjoy non dining hall cooked food while it lasts!",
        f"☀️ **{days(left)}** of summer left. go get a tan or a sunburn or melanoma, your choice!",
        f"🎓 **{days(left)}** until Fall semester starts. immunization requirement RFK says is bad!",
        f"🐾 **{days(left)}** left until classes. send a meme to your RA if they emailed you",
        f"📚 **{days(left)}** until Fall 2026 begins. Glup glup",
        f"🌊 **{days(left)}** of summer remaining. arf arf arf growl!",
        f"🐾 **{days(left)}** left. white claw",
        f"🎒 **{days(left)}** until classes start. enjoy your summer bed....",
        f"🐾 **{days(left)}** until Fall 2026. ar eyou working or chilling?",
        f"🎓 **{days(left)}** left of summer. sooooo strwessful! >-<!",
    ])


class StartCog(commands.Cog, name="Start"):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        self.last_announcement_bucket: str | None = None
        self.morning_task.start()
        self.evening_task.start()
        print("Start Cog Ready")

    def cog_unload(self):
        self.morning_task.cancel()
        self.evening_task.cancel()

    async def _post_scheduled(self):
        now = datetime.now(ET)
        today = now.date()

        bucket = now.strftime("%Y-%m-%d-%H")
        if bucket == self.last_announcement_bucket:
            return

        # Ignore delayed/catch-up runs after resume.
        if now.minute > 5:
            return

        msg = build_message(today)
        if msg is None:
            return
        channel = self.bot.get_channel(GENERAL_CHANNEL_ID)
        if isinstance(channel, discord.TextChannel):
            await channel.send(msg)
            self.last_announcement_bucket = bucket

    @tasks.loop(time=[time(10, 0, tzinfo=ET)])
    async def morning_task(self):
        await self._post_scheduled()

    @morning_task.before_loop
    async def before_morning(self):
        await self.bot.wait_until_ready()

    @tasks.loop(time=[time(17, 0, tzinfo=ET)])
    async def evening_task(self):
        await self._post_scheduled()

    @evening_task.before_loop
    async def before_evening(self):
        await self.bot.wait_until_ready()

    @commands.command()
    async def start(self, ctx: Context):
        """How many days until classes start?"""
        today = datetime.now(ET).date()
        msg = build_message(today)
        if msg is None:
            await ctx.send("📚 Classes have started! Good luck this semester, Terriers. 🐾")
            return
        await ctx.send(msg)

    @app_commands.command(name="start", description="How many days until classes start?")
    async def start_slash(self, interaction: discord.Interaction):
        today = datetime.now(ET).date()
        msg = build_message(today)
        if msg is None:
            await interaction.response.send_message("📚 Classes have started! Good luck this semester, Terriers. 🐾")
            return
        await interaction.response.send_message(msg)


async def setup(bot: TerrierBot):
    await bot.add_cog(StartCog(bot))
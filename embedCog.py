import json as _json

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot


async def setup(bot: TerrierBot):
    await bot.add_cog(EmbedCog(bot))


def _build_embedreg_sequence() -> list[discord.Embed]:
    embed1 = discord.Embed(
        color=discord.Color(0x5865F2),
        title="Incoming Student Course Registration is SOON (June 9th and June 11th @ 9am EST)",
        description=(
            "My little gumdrops,\n\n"
            "Welcome to BU! I know that communication before getting to campus can be spotty and confusing, but I am here to help! "
            "You can share this post with other gumdrops you know too!\n\n"
            "If you are not aware, registration for your fall 2026 courses begins on June 9th at 9am EST for **transfers** and June 11th "
            "at 9am EST for **first-years** (if you're in a different time zone, note the difference!). Registration will remain open "
            "through the beginning of September, so you can switch your classes, add classes, drop classes, etc with 0 consequences and "
            "0 visibility on your transcript up through the beginning of the school year!\n\n"
            "It is HIGHLY recommended that you register as soon as you are able in order to grab the classes/times you want, but course "
            "registration is very flexible!\n\n"
            "View your registration time in your timezone:\n"
            "Transfer Students: <t:1781010000:t>\n"
            "First-Year Students: <t:1781182800:t>"
        ),
    )

    embed2 = discord.Embed(
        color=discord.Color(0x8B6BE8),
        title="✅ Your Tasks for RIGHT NOW! — Part 1: Figure out what classes to take!",
    )
    embed2.add_field(
        name="College Guides",
        value=(
            "Most programs have guides online to help you make decisions.\n"
            "[CAS/Pardee](https://sites.bu.edu/casreg/registration-guide-by-major/) • [Questrom](https://questromworld.bu.edu/orientation/) "
            "• [Sargent](https://bu.edu/sargent/admissions/undergraduate/admitted/sargent-college-orientation/) "
            "• [ENG](https://bu.edu/eng/academics/resources/undergraduate-student-resources/checklist-for-incoming-bu-eng-students/registration-for-incoming-eng-freshmen/) "
            "• [CDS](https://bu.edu/cds-faculty/programs-admissions/undergraduate/registration-guide-for-the-data-science-major%E2%80%AF/) "
            "• [CFA](https://bu.edu/cfa/students/incoming-undergraduate-resources/) "
            "• [COM](https://bu.edu/com/for-current-students/undergraduate-advising/registration/) "
            "• [Wheelock](https://bu.edu/wheelock/resources/students/undergraduate-students/program-plans/) "
            "• [KHC](https://bu.edu/khc/admissions/welcome-class-of/)\n"
            "Some are more helpful than others..."
        ),
        inline=False,
    )
    embed2.add_field(
        name="The Bulletin",
        value="This is called [the bulletin](https://www.bu.edu/academics/bulletin/). It is your best friend. It is the official and most up to date place to see your degree requirements.",
        inline=False,
    )
    embed2.add_field(
        name="AP / IB Scores",
        value=(
            "If you are waiting on AP or IB scores, it is recommended that you guess your score and register accordingly. "
            "If you didn't get the score you expected, you can change your classes!\n"
            "[AP credit chart](https://www.bu.edu/admissions/files/2018/06/Advanced-Credit-Guide.pdf) • "
            "[IB credit chart](https://www.bu.edu/admissions/files/2018/05/ib_course_equivalence.pdf)"
        ),
        inline=False,
    )
    embed2.add_field(
        name="First-Year Writing",
        value=(
            "First-year writing has special restrictions if you submitted a TOEFL or alternative English language exam. "
            "[Read here](https://www.bu.edu/writingprogram/curriculum/placement/)\n"
            "[WR120 Topics for Everyone](https://www.bu.edu/writingprogram/curriculum/schedule/)"
        ),
        inline=False,
    )
    embed2.add_field(
        name="Wtf is the HUB?",
        value=(
            "The HUB is BU's gen ed system. Instead of saying you need to take this math, this english, and this science, the HUB allows "
            "more flexibility by assigning HUB requirements to nearly every class at BU.\n"
            "[See what classes give what](https://www.bu.edu/hub/hub-courses/)\n"
            "There are 26 requirements that you need to fill. HOWEVER! Since every class you take has between 0-3 HUB requirements, "
            "you will get most of them done via your major classes. I would say that something like 6-8 courses outside of your major "
            "will get it all done.\n"
            "Note: The transfer HUB is different and shorter.\n"
            "[Read more here](https://www.bu.edu/hub/hub-requirements/hub-requirements-for-entering-first-year-students/)"
        ),
        inline=False,
    )
    embed2.add_field(
        name="Course Load",
        value="A typical course load is 16 credits, or four 4-credit classes. However you can take up to 18 credits for free! I don't recommend taking under 16 your first semester.",
        inline=False,
    )
    embed2.add_field(
        name="Other Notes",
        value=(
            "Your schedule will be unique to your background, interests, and experiences! There is no 1 prescribed way to pick your classes!\n"
            "There are also advisors that can help, but they have a huge stack of students reaching out to them with questions so expect a delay.\n"
            "Can't figure it out? DM me your major and any AP/IB credits you expect and I can give you a suggestion! "
            "I respond faster and more accurately lol"
        ),
        inline=False,
    )

    embed3 = discord.Embed(
        color=discord.Color(0xC46ED4),
        title="✅ Your Tasks for RIGHT NOW! — Part 2: Pick your times and professors + Register!",
    )
    embed3.add_field(
        name="1. Check for Holds",
        value=(
            "MAKE SURE you have met all the requirements to register. If you have a \"Hold\" on your account, you won't be able to register.\n"
            "[These are the requirements](https://www.bu.edu/reg/registration/requirements/)\n"
            "Incoming students have a grace period, so you don't need to do your immunizations or alcohol training before registering. "
            "MyBU will tell you very clearly if you have a hold."
        ),
        inline=False,
    )
    embed3.add_field(
        name="2. Learn how to use MyBU",
        value=(
            "[Log in to MyBU](https://student.bu.edu/MyBU/)\n"
            "CAS has a pretty decent [step by step guide](https://sites.bu.edu/casreg/registration-instructions/) on how to add classes "
            "to your Schedule Builder. This is where you will mess around with different schedules.\n"
            "Once you've decided on your favorite schedule, add it to your Shopping Cart. From here, you can register automatically once 9am EST hits!"
        ),
        inline=False,
    )
    embed3.add_field(
        name="3. How to pick classes",
        value=(
            "Read [Rate My Professors](https://www.ratemyprofessors.com/) reviews from past students\n"
            "Don't do an 8am if you can't wake up at 8AM\n"
            "Many classes require you to register for a lab and/or a discussion in addition to the lecture. Make sure you register for all "
            "of the components needed!\n"
            "Some classes may be \"Restricted\" to a certain group, meaning you can't register for it. Contact the department if you really want that class.\n"
            "You can get from one end of campus to the other in 15 minutes. It is fine to put classes one after another (but too many in a row might be overwhelming!)"
        ),
        inline=False,
    )
    embed3.add_field(
        name="4. Register!",
        value=(
            "Set an alarm for 9am EST!\n"
            "Log in to MyBU, use your Schedule Builder and Shopping Cart to officially enroll!\n"
            "Courses in your schedule builder or shopping cart are not official until you click enroll!\n"
            "Go into registration with a few backups planned, and remember that nothing about registration is final or permanent!"
        ),
        inline=False,
    )
    embed3.add_field(
        name="Full classes?",
        value=(
            "If your preferred class is full, you can add yourself to a waitlist— definitely do this!\n"
            "If a required class is full, email your advisor— they might be able to squeeze you in!"
        ),
        inline=False,
    )

    embed4 = discord.Embed(
        color=discord.Color(0xF47EB0),
        title="*** Tips from me! ***",
        description=(
            "**You are undecided.** I do not care if you have wanted to be a doctor since you were 4, you are in a new environment and it is "
            "THE BEST time for you to dig deep and learn about yourself and your true passions. You are not stuck in your major/school, and "
            "70% of students will change their major AT LEAST once. I highly highly highly recommend using your electives/choice classes to "
            "explore topics that you have always found interesting. Now is the best time to do that! You might even decide to pursue a minor "
            "in that topic!\n\n"
            "**Flexibility is key.** It is tempting to try to optimize your schedule and refine your path to the quickest possible way. "
            "However, things will not go your way. It might not be this registration that goes awry, but your path will have plenty of bumps "
            "and you will need to pivot and re-assess where you are. This is FINE! Don't panic!\n\n"
            "**You are not forced to register within your major, or follow your advisor's guidance.** Be reasonable... But if you know you're "
            "gonna be a math major but you're in journalism right now, take the math classes! You are responsible for your own education, "
            "which is fantastic but also dangerous.\n\n"
            "**Build Community!** Taking classes with students in your major is a great way to make connections and find study buddies! Talk "
            "to the people sitting near you in class— I promise they want to get your contact info to ask for help on homeworks or meet up to "
            "study. Also, taking classes across different schools/departments can help you meet non-majors and break out of your bubble!\n\n"
            "**FY101** is a cool 1-credit option that is designed for the primary purpose of giving you built in friends and a range of "
            "connections/resources. Highly recommend!\n\n"
            "**Shop.** During the first few weeks of classes, you can drop classes, add classes, go to random lectures to see what they are "
            "like, and explore options. If the professor is a mess or the class is not for you, there is 0 shame in dropping and swapping. "
            "You won't be offending the professor, and it can be a very strategic/smart choice.\n\n"
            "If anyone has any questions, please feel free to message me or other members of the server with are in your major for feedback!"
            "This is exciting! Don't stress out over this, and know that you can't \"mess up\" at registration. There is nothing you and your "
            "advisor can't fix!\n\n"
            "Good luck jellybeans! ❤️\n\n"
            "— OwO"
        ),
    )

    return [embed1, embed2, embed3, embed4]


def _build_embedhousing_sequence() -> list[discord.Embed]:
    embed1 = discord.Embed(
        color=discord.Color(0x93E5C8),
        title="🏠 Housing FAQ",
        description=(
            "Got housing questions? Here's everything you need to know "
        ),
    )

    embed2 = discord.Embed(
        color=discord.Color(0x81BCB9),
        title="🏠 Housing FAQ — Part 1: The Basics",
    )
    embed2.add_field(
        name="Wait I hate my housing, how do I change it?",
        value=(
            "You really can't, but here's what you can try:\n"
            "1. Email housing and ask nicely\n"
            "2. Find someone to direct swap with\n"
            "3. Deal with it"
        ),
        inline=False,
    )
    embed2.add_field(
        name="Is [insert building name] really that bad?",
        value=(
            "All buildings have their pros/cons, but nothing at BU is absolutely terrible. "
            "Maybe you're used to more luxury, but living in even the freshmen dorms is a great "
            "experience! You'll meet lots of new people and learn about who you are as you adapt "
            "to being away from home. So no, it's not that bad."
        ),
        inline=False,
    )
    embed2.add_field(
        name="What is my dorm assignment like?",
        value="[Read more here](https://sites.google.com/view/directswapconnections/housing-options)",
        inline=False,
    )
    embed2.add_field(
        name="How do I find my roommate's email?",
        value=(
            "You should have their name. With their name, start by looking on the "
            "[BU directory](https://www.bu.edu/directory). If you can't find them there, "
            "search for their Instagram, LinkedIn, or Facebook. Usually there are traces "
            "of people online!"
        ),
        inline=False,
    )
    embed2.add_field(
        name="What do I pack?",
        value=(
            "Here's the packing list. Consider buying things once you get to campus!\n"
            "[BU's official packing guide](https://www.bu.edu/housing/living/what-to-bring/) • "
            "[Packing checklist (Google Sheet)](https://docs.google.com/spreadsheets/d/1wycbvhXoJmffzKJz5RxjdVc4HeLxWd_nIOt_sPYVS0E/edit?usp=drive_link) • "
            "[Parents' packing list](https://www.bu.edu/parentsprogram/resources/college-packing-list/)"
        ),
        inline=False,
    )

    embed3 = discord.Embed(
        color=discord.Color(0x6F92AA),
        title="🏠 Housing FAQ — Part 2: Logistics & Living",
    )
    embed3.add_field(
        name="Fenway/West/Danielsen is SOOOOOO FAR from my classes!!!! What do I do?",
        value="There are shuttles, and walking is great for your physical and mental wellbeing! None of it is really that far!",
        inline=False,
    )
    embed3.add_field(
        name="How do I survive in the summer without AC?",
        value=(
            "Fans. Many fans. Keep the curtains closed in the day to keep the heat out. "
            "Know that you'll be complaining about the cold in 2 weeks...."
        ),
        inline=False,
    )
    embed3.add_field(
        name="How do I make friends?",
        value=(
            "Everyone on your floor is in the same boat as you! They're in a new environment "
            "surrounded by strangers and they desperately want to find people to connect with! "
            "I recommend putting your social media/phone on your door so people can add you, "
            "and whenever you see someone, introduce yourself. If you want to walk around campus "
            "or get lunch, grab someone from your floor by knocking on doors or wandering around "
            "until you find someone, and bring them with you. KEEP YOUR DOOR OPEN WHEN YOU ARE IN! "
            "I promise everyone else is scared and insecure about making friends (just like you!)"
        ),
        inline=False,
    )
    embed3.add_field(
        name="What if I don't like my roommate???",
        value=(
            "Guess what, no one expects you to be lifelong BFFs with your freshman year roomie! "
            "You can coexist and that is a perfectly normal and valid way to live together! If "
            "there is hostility or conflict, start by openly communicating! Agree on rules and "
            "courtesies you'll both practice... not everyone has the same expectations or cultural "
            "standards for living together, and you might need to compromise a bit. If "
            "communicating doesn't work, have an honest conversation with your RA, who can serve "
            "as a mediator to help you guys out! This is normal!"
        ),
        inline=False,
    )

    embed4 = discord.Embed(
        color=discord.Color(0x5D689B),
        title="🏠 Housing FAQ — Part 3: Stuff & Rules",
    )
    embed4.add_field(
        name="Do I need to bring a fridge or microwave?",
        value=(
            "BU offers microfridge rentals. If you have a roommate, communicate with them so you "
            "don't both get them! You're allowed to bring your own mini fridge, however, "
            "microwaves (that are NOT part of the microfridge) are not allowed."
        ),
        inline=False,
    )
    embed4.add_field(
        name="Can I bring my pet!!!!!",
        value="Girl. No.",
        inline=False,
    )
    embed4.add_field(
        name="Who's going to stop me from bringing beer, my pet hamster, and a microwave?",
        value=(
            "Actually, BU has the right to enter your space for any reason at any time! They "
            "have the right to open the drawers of the BU furniture (i.e. the dresser). However, "
            "they cannot open your personal belongings, such as a suitcase or storage unit you "
            "bring. Please don't be an idiot."
        ),
        inline=False,
    )
    embed4.add_field(
        name="Can I order Amazon to my dorm?",
        value="Yes! Your shipping address is in your housing portal.",
        inline=False,
    )
    embed4.add_field(
        name="Wait, housing came out?",
        value="Yes, for some people. Be patient if you haven't received it!",
        inline=False,
    )

    embed5 = discord.Embed(
        color=discord.Color(0x4B3F8C),
        title="🚿 I'm scared of the communal bathrooms!",
        description="That's completely normal! It just takes some getting used to. Here are some tips:",
    )
    embed5.add_field(
        name="Showers (cs majors please disregard)",
        value=(
            "• Always wear shower shoes, preferably ones with holes in them\n"
            "• Indicate you're in the shower by hanging your shower caddy on the door/wall or "
            "placing it inside the shower or right outside your door\n"
            "• You can hang your robe/towel on the hook outside your door! Consider getting a "
            "robe to walk back to your dorm room!"
        ),
        inline=False,
    )
    embed5.add_field(
        name="Toilets & Sinks",
        value=(
            "• Some people are bad at cleaning up after themselves, so please don't add to the issue\n"
            "• Please don't dump things down the sink: it can clog, plus there's remnants of food, etc.\n"
            "• Wash your hands!"
        ),
        inline=False,
    )
    embed5.add_field(
        name="General",
        value=(
            "Do you care when you see someone brushing their teeth or shaving at a sink? No? "
            "Then why do you think anyone else cares about you. Everyone has to do their business "
            "in there, and caring about others is way too much effort."
        ),
        inline=False,
    )

    return [embed1, embed2, embed3, embed4, embed5]


class EmbedModal(discord.ui.Modal, title="Send Embed"):
    embed_title = discord.ui.TextInput(
        label="Title",
        placeholder="Embed title (optional)",
        required=False,
        max_length=256,
    )
    description = discord.ui.TextInput(
        label="Body (supports # headings, **bold**)",
        placeholder="# Big heading\n## Smaller heading\n\nRegular text, **bold**, *italic*, > quote...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=4000,
    )
    description2 = discord.ui.TextInput(
        label="Body (cont.)",
        placeholder="Continued text here...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1024,
    )
    color = discord.ui.TextInput(
        label="Color (hex, e.g. #cc0000)",
        placeholder="#cc0000",
        required=False,
        max_length=10,
    )
    footer = discord.ui.TextInput(
        label="Footer",
        placeholder="Footer text (optional)",
        required=False,
        max_length=2048,
    )

    def __init__(self, target: discord.abc.Messageable):
        super().__init__()
        self.target = target

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed()
        if self.embed_title.value:
            embed.title = self.embed_title.value
        if self.description.value:
            embed.description = self.description.value
        if self.color.value:
            try:
                embed.color = discord.Color(int(self.color.value.lstrip("#").lstrip("0x"), 16))
            except ValueError:
                await interaction.response.send_message("Invalid color — use hex like `#cc0000`.", ephemeral=True)
                return
        if self.description2.value:
            embed.add_field(name="\u200b", value=self.description2.value, inline=False)
        if self.footer.value:
            embed.set_footer(text=self.footer.value)
        await self.target.send(embed=embed)
        await interaction.response.send_message("Embed sent! ✅", ephemeral=True)


class EmbedCog(commands.Cog, name="Embed", description="Send rich embeds. Owner only."):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        print("Embed Cog Ready")

    @app_commands.command(name="embed", description="Send a rich embed. (Owner only)")
    @app_commands.describe(channel="Channel to send the embed to (defaults to current channel)")
    async def embed_slash(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("That command is not for you.", ephemeral=True)
            return
        target: discord.abc.Messageable = channel or interaction.channel  # type: ignore[assignment]
        await interaction.response.send_modal(EmbedModal(target))

    @commands.command(name="embed")
    @commands.is_owner()
    async def send_embed(self, ctx: Context, channel: discord.TextChannel | None = None, *, json_text: str = ""):
        """Send one or more rich embeds via JSON inline or attached file. (Owner only)

        Formats:
          Single:   {"title": "...", "description": "..."}
          Array:    [{"title": "Part 1"}, {"title": "Part 2"}]
          Gradient: {"gradient": ["#ff0000", "#0000ff"], "embeds": [{...}, {...}]}

        Per-embed fields: title, description, color (hex or int), footer,
        thumbnail (url), image (url), fields (list of {name, value, inline}).
        """
        if ctx.message.attachments:
            raw = await ctx.message.attachments[0].read()
            json_text = raw.decode("utf-8")

        if not json_text.strip():
            _ = await ctx.send("Provide JSON inline or attach a .json/.txt file.")
            return

        try:
            data = _json.loads(json_text)
        except _json.JSONDecodeError as e:
            _ = await ctx.send(f"Invalid JSON: {e}")
            return

        gradient_stops: list[tuple[int, int, int]] | None = None

        if isinstance(data, dict) and "embeds" in data:
            # Wrapper object — may have gradient
            raw_stops = data.get("gradient")
            if raw_stops and isinstance(raw_stops, list) and len(raw_stops) >= 2:
                def hex_to_rgb(h: str) -> tuple[int, int, int]:
                    v = int(str(h).lstrip("#").lstrip("0x"), 16)
                    return (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF
                gradient_stops = [hex_to_rgb(s) for s in raw_stops]
            items = data["embeds"]
            if not isinstance(items, list):
                items = [items]
        elif isinstance(data, dict):
            items = [data]
        elif isinstance(data, list):
            items = data
        else:
            _ = await ctx.send("JSON must be an object `{...}` or array `[...]`.")
            return

        def lerp_color(stops: list[tuple[int, int, int]], t: float) -> discord.Color:
            """Interpolate across multiple color stops. t in [0, 1]."""
            if len(stops) == 1:
                return discord.Color(stops[0][0] << 16 | stops[0][1] << 8 | stops[0][2])
            segment = t * (len(stops) - 1)
            lo = int(segment)
            hi = min(lo + 1, len(stops) - 1)
            local_t = segment - lo
            r = round(stops[lo][0] + (stops[hi][0] - stops[lo][0]) * local_t)
            g = round(stops[lo][1] + (stops[hi][1] - stops[lo][1]) * local_t)
            b = round(stops[lo][2] + (stops[hi][2] - stops[lo][2]) * local_t)
            return discord.Color(r << 16 | g << 8 | b)

        def build_embed(d: dict, color_override: discord.Color | None = None) -> discord.Embed:
            embed = discord.Embed()
            if title := d.get("title"):
                embed.title = str(title)
            if description := d.get("description"):
                embed.description = str(description)
            if color_override is not None:
                embed.color = color_override
            elif (color := d.get("color")) is not None:
                if isinstance(color, str):
                    color = int(color.lstrip("#").lstrip("0x"), 16)
                embed.color = discord.Color(int(color))
            if footer := d.get("footer"):
                embed.set_footer(text=str(footer))
            if thumbnail := d.get("thumbnail"):
                embed.set_thumbnail(url=str(thumbnail))
            if image := d.get("image"):
                embed.set_image(url=str(image))
            for field in d.get("fields", []):
                embed.add_field(
                    name=str(field.get("name", "") or "\u200b"),
                    value=str(field.get("value", "") or "\u200b"),
                    inline=bool(field.get("inline", False)),
                )
            return embed

        valid_items = [item for item in items if isinstance(item, dict)]
        n = len(valid_items)
        embeds: list[discord.Embed] = []
        for i, item in enumerate(valid_items):
            override = None
            if gradient_stops:
                t = i / (n - 1) if n > 1 else 0.0
                override = lerp_color(gradient_stops, t)
            embeds.append(build_embed(item, override))

        if not embeds:
            _ = await ctx.send("No valid embed objects found.")
            return

        target: discord.abc.Messageable = channel or ctx.channel
        for i in range(0, len(embeds), 10):
            await target.send(embeds=embeds[i:i+10])
        if channel is not None:
            await ctx.message.add_reaction("✅")

    @commands.command(name="embedreg")
    async def embedreg(self, ctx: Context):
        """Delete trigger message and post the registration embed sequence."""
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        for embed in _build_embedreg_sequence():
            await ctx.channel.send(embed=embed)

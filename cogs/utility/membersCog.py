import csv
import io
import discord
from discord.ext import commands
from bot import TerrierBot, Context


def _normalize_role_name(value: str) -> str:
    text = value.strip()
    if text.startswith("@"):
        text = text[1:]
    return " ".join(text.split()).lower()

async def setup(bot: TerrierBot):
    await bot.add_cog(MembersCog(bot))

class MembersCog(commands.Cog, name="Members", description="Member exports and manual-prune reporting tools."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        self.prune_role_id = 1474070492548956170
        self.category_roles_csv_path = "data/Category Roles - Copy of Sheet1.csv"
        print("Members Cog Ready")

    def _load_category_role_map(self) -> tuple[list[str], dict[str, set[str]]]:
        with open(self.category_roles_csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise ValueError("Category roles CSV has no header row")

            categories = [name.strip() for name in reader.fieldnames if name and name.strip()]
            category_to_roles: dict[str, set[str]] = {category: set() for category in categories}

            for row in reader:
                for category in categories:
                    cell = row.get(category, "")
                    if not isinstance(cell, str):
                        continue
                    normalized = _normalize_role_name(cell)
                    if normalized:
                        category_to_roles[category].add(normalized)

            return categories, category_to_roles

    @commands.command()
    @commands.is_owner()
    @commands.guild_only()
    async def exportmembers(self, ctx: Context):
        """Export all server members to a CSV file."""
        assert ctx.guild is not None

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Username", "Global Display Name", "Server Nickname", "Roles", "Joined At"])

        async for member in ctx.guild.fetch_members(limit=None):
            roles = [r.name for r in member.roles if r.name != "@everyone"]
            joined = member.joined_at.strftime("%Y-%m-%d %H:%M:%S") if member.joined_at else ""
            writer.writerow([
                member.name,
                member.global_name or "",
                member.nick or "",
                ", ".join(roles),
                joined,
            ])

        output.seek(0)
        file = discord.File(fp=io.BytesIO(output.getvalue().encode()), filename="members.csv")
        await ctx.send("Here are the server members:", file=file)

    @commands.command()
    @commands.is_owner()
    @commands.guild_only()
    async def exportprunecandidates(self, ctx: Context):
        """Export members with no roles or only role ID 1474070492548956170."""
        assert ctx.guild is not None

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Username",
            "Global Display Name",
            "Server Nickname",
            "Roles",
            "Joined At",
            "Member ID",
        ])

        candidate_count = 0
        async for member in ctx.guild.fetch_members(limit=None):
            if member.bot:
                continue

            extra_roles = [role for role in member.roles if role != ctx.guild.default_role]
            has_no_extra_roles = len(extra_roles) == 0
            has_only_prune_role = len(extra_roles) == 1 and extra_roles[0].id == self.prune_role_id

            if not (has_no_extra_roles or has_only_prune_role):
                continue

            joined = member.joined_at.strftime("%Y-%m-%d %H:%M:%S") if member.joined_at else ""
            writer.writerow([
                member.name,
                member.global_name or "",
                member.nick or "",
                ", ".join(role.name for role in extra_roles),
                joined,
                member.id,
            ])
            candidate_count += 1

        output.seek(0)
        file = discord.File(
            fp=io.BytesIO(output.getvalue().encode()),
            filename="prune_candidates_role_filter_only.csv",
        )
        await ctx.send(
            f"Found {candidate_count} prune candidates using role filter only.",
            file=file,
        )

    @commands.command()
    @commands.is_owner()
    @commands.guild_only()
    async def addugrad(self, ctx: Context):
        """One-off: give a hardcoded role to a hardcoded list of user IDs."""
        assert ctx.guild is not None

        role_id = 1401917785646301256
        user_ids = [
            456217569028734988, 910790517405679617, 292538018835726346, 1508867075790213314,
            1497146972736327741, 1415349512053981224, 1398524800858587228, 1240449530340704320,
            967292721054248960, 944005383213678655, 913972192147017758, 784224294493356095,
            498827895339483137, 446127319946362890, 406074051119939585, 1509368675017298181,
            1506884982755557446, 1502493519657435269, 1497630258013147346, 1494500692360958054,
            1428484546562756710, 1427508519619526730, 1335306778124222475, 1174279204964147273,
            1023288216352194580, 932839746537918524, 904435202267414569, 818640371461390427,
            816867004698591262, 779496747671879690, 743674139616870500, 722658568309964810,
            719682961624137788, 716834608175644672, 701590929747738664, 687721646081310720,
            578033588415627274, 576553764195008563, 550130803720454169, 1470561647176450150,
            1458942250439413761, 1456687589342839150, 1451028868684189730, 1451028721862574213,
            1450681484448108627, 1450324073207959565, 1446327557292294234, 1421163285268664390,
            1345916279508439080, 1308821611784175646, 1255214758475599952, 1188943698008997950,
            1149160698316849172, 1100582352721281154, 988781193707274281, 954940805448106004,
            932384803855151114, 877928505394987038, 876239391239061504, 852601550835941376,
            852546486134898718, 842959261641867315, 840029163007639575, 821216901162205184,
            798017756137127986,
        ]

        role = ctx.guild.get_role(role_id)
        if role is None:
            await ctx.send(f"Couldn't find role `{role_id}` in this server.")
            return

        added, already_had, not_found, failed = 0, 0, [], []
        for user_id in user_ids:
            member = ctx.guild.get_member(user_id)
            if member is None:
                try:
                    member = await ctx.guild.fetch_member(user_id)
                except discord.NotFound:
                    not_found.append(user_id)
                    continue
                except discord.HTTPException:
                    failed.append(user_id)
                    continue

            if role in member.roles:
                already_had += 1
                continue

            try:
                await member.add_roles(role, reason="addugrad bulk role add")
                added += 1
            except (discord.Forbidden, discord.HTTPException):
                failed.append(user_id)

        summary = [
            f"Added role to {added} member(s).",
            f"{already_had} already had it.",
        ]
        if not_found:
            summary.append(f"{len(not_found)} not in server: {', '.join(map(str, not_found))}")
        if failed:
            summary.append(f"{len(failed)} failed: {', '.join(map(str, failed))}")

        await ctx.send("\n".join(summary))

    @commands.command()
    @commands.is_owner()
    @commands.guild_only()
    async def exportmembersbycategory(self, ctx: Context):
        """Export members with roles grouped into columns from the Category Roles CSV."""
        assert ctx.guild is not None

        try:
            categories, category_to_roles = self._load_category_role_map()
        except FileNotFoundError:
            await ctx.send(f"Could not find `{self.category_roles_csv_path}` in the bot folder.")
            return
        except ValueError as exc:
            await ctx.send(str(exc))
            return

        output = io.StringIO()
        writer = csv.writer(output)
        header = [
            "Discord Name",
            "Discord ID",
            "Display Name",
            "Server Name",
            "Joined At",
            *categories,
        ]
        writer.writerow(header)

        async for member in ctx.guild.fetch_members(limit=None):
            member_roles = [role.name for role in member.roles if role != ctx.guild.default_role]
            role_name_by_normalized: dict[str, str] = {
                _normalize_role_name(role_name): role_name for role_name in member_roles
            }

            joined = (
                member.joined_at.strftime("%Y-%m-%d %H:%M:%S (%A)")
                if member.joined_at
                else ""
            )

            category_cells: list[str] = []
            for category in categories:
                matched = sorted(
                    role_name_by_normalized[norm]
                    for norm in role_name_by_normalized
                    if norm in category_to_roles[category]
                )
                category_cells.append(", ".join(matched))

            writer.writerow([
                member.name,
                member.id,
                member.display_name,
                member.nick or "",
                joined,
                *category_cells,
            ])

        output.seek(0)
        file = discord.File(
            fp=io.BytesIO(output.getvalue().encode("utf-8")),
            filename="members_by_category_roles.csv",
        )
        await ctx.send("Here is the categorized member export:", file=file)

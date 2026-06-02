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
        self.category_roles_csv_path = "Category Roles - Copy of Sheet1.csv"
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

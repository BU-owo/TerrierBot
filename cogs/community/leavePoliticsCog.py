import discord
from discord.ext import commands

POLITICS_ROLE_ID = 1477468718127775824


class LeaveConfirmView(discord.ui.View):
    def __init__(self, member: discord.Member, role: discord.Role):
        super().__init__(timeout=30)
        self.member = member
        self.role = role
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.member.id:
            await interaction.response.send_message("This isn't your confirmation to click.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Leave Politics", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        for child in self.children:
            child.disabled = True
        try:
            await self.member.remove_roles(self.role, reason="Self-removed via =leavepolitics/leavepolitics")
            await interaction.response.edit_message(
                content="You've left Politics. You'll need to re-apply to get back into the channel.",
                view=self,
            )
        except discord.Forbidden:
            await interaction.response.edit_message(
                content="Couldn't remove the role — I might be missing permissions. Ping a mod.",
                view=self,
            )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Cancelled — you're still in Politics.", view=self)
        self.stop()


class LeavePoliticsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="leavepolitics", description="Leave the Politics role/channel")
    async def leavepolitics(self, ctx: commands.Context):
        """Leave the Politics role (you'll need to re-apply to get back in)."""
        role = ctx.guild.get_role(POLITICS_ROLE_ID)
        if role is None:
            await ctx.send("Couldn't find the Politics role — ping a mod.", ephemeral=True)
            return

        member = ctx.author
        if role not in member.roles:
            await ctx.send("You're not in Politics.", ephemeral=True)
            return

        view = LeaveConfirmView(member, role)
        await ctx.send(
            "Are you sure? You'll need to re-apply to get back into the politics channel.",
            view=view,
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(LeavePoliticsCog(bot))
import discord


async def get_role(guild: discord.Guild, role_name: str):
    return next(role for role in guild.roles if role_name == role.name)

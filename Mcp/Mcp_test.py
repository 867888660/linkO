import asyncio, os, platform
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

TAVILY_KEY = "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"

def make_server_params() -> StdioServerParameters:
    env = os.environ.copy()                    # 保留 PATH，避免 npx 解析失败
    env["TAVILY_API_KEY"] = TAVILY_KEY
    is_win = platform.system() == "Windows"
    return StdioServerParameters(
        command="cmd" if is_win else "npx",
        args=["/c", "npx", "-y", "调用名称"] if is_win
             else ["-y", "调用名称"],
        env=env, timeout=15000,
    )

async def main():
    async with stdio_client(make_server_params()) as (r, w):
        async with ClientSession(r, w) as sess:
            await sess.initialize()

            out = await sess.call_tool(
                "get_file_info",
                arguments={
                    "path": "C:\\Users\\YMXD\\Desktop\\linkO\\linkel\\Mcp\\McpList.json"
                },
            )

            print(out.content)

if __name__ == "__main__":
    asyncio.run(main())

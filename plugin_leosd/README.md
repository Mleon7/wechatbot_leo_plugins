参考：https://github.com/lanvent/plugin_sdwebui.git

修改部分：

1. 简化用户输入
2. 借助gpt3.5-turbo翻译用户输入成符合stable diffusion 的prompt
3. 将更换模型和绘图分开
4. 在更换模型和绘图过程中禁用用户输入，防止电脑卡死
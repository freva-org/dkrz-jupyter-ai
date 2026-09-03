# AGENTS.md

This repository contains a forked version of jupyter-ai v2, called "dkrz-jupyter-ai".
It is supposed to replace the "jupyter-ai" and "jupyter-ai-magics" packages for use at the DKRZ,
as well as introduce a chat provider for the DKRZ chatbot "climateclaw".

## Repo info 
Remote: https://github.com/freva-org/dkrz-jupyter-ai
Upstream repository: https://github.com/jupyterlab/jupyter-ai/
Upstream branch for synchronization: 2.x

## Environment and lodcal development setup instructions 
1. conda create -p /tmp/jupyter_ai -c conda-forge python=3.12 nodejs=20
2. conda activate /tmp/jupyter_ai/
3. ./scripts/install.sh
4. jlpm
5. jlpm build

## Project structure
The most important components are located under packages/:
1. packages/jupyter-ai: core jupyter-ai package, including ui components
2. packages/jupyter-ai-magics: jupyter-ai backend components, including jupyter-ai inline magic methods
3. packages/climateclaw-provider: custom provider for ClimateClaw chatbot for jupyter-ai



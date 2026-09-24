#### Setting up the Jupyter-AI extension for use on the DKRZ JupyterHub

1. In a terminal, please log on to Levante, by running the following command:
```bash
ssh <username>@levante.dkrz.de
```
2. Once logged in, run the following command to set up the Jupyter-AI extension, plus extras:
```bash
module load clint climateclaw
```
This command downloads and installs the dependencies needed for Jupyter-AI and ClimateClaw, creates a IPython Kernel for use of the chatbot within a notebook and creates an example notebook in `~/jupyter-ai-examples`.

#### Using Jupyter-AI on the DKRZ JupyterHub
1. Open the DKRZ JupyterHub in a web browser: https://jupyterhub.dkrz.de
2. Log in with your username and password.
3. Onced logged in start a server by clicking on **Start** in the Preset column
![alt_text](https://github.com/user-attachments/assets/a0e377bc-9e09-45c0-8862-7dc4b6b4010a)
4. In the opened dialogue, please leave the default settings. **Important** You need to enter a valid project (`ch0636`) (connected to your DKRZ account) to be able to spawn a Jupyter Lab instance:
![alt_text](https://github.com/user-attachments/assets/f5888984-0bf8-44ea-ad9e-c2319a6749a7)
5. After a while JupyterHub should successfully spawn a Jupyter Lab Server and you should be forwarded to it. The result should look something like this:
![alt_text](https://github.com/user-attachments/assets/5dd7a940-efc4-461b-9032-b57fa45aa6a1)
6. By clicking on the speech bubble icon, the chat interface can be opened:
![alt_text](https://github.com/user-attachments/assets/f76f0250-1f02-4481-aa64-2c09549afd50)
7. Before being able to talk to the chatbot, we need to authenticate our user first. Do this by typing `/login` in the chat window. The chatbot should respond with a link that can be opened to authenticate. 
8. After logging in, you can return to the Jupyter Lab window and start your first interaction with the bot!

### Using Jupyter-AI within notebooks
Jupyter-AI can be used within a jupyter notebook (using the chat interface, as well as so-called "jupyter magics"). An example on how to do this can be found under `~./jupyter-ai-examples/jupyter_ai_magics.ipynb`.
For further instructions, please refer to the [official documentation](https://jupyter-ai.readthedocs.io/en/v2/users/index.html#the-ai-and-ai-magic-commands).
To use the jupyter-ai magics, please open a notebook using the "ClimateClaw" kernel that should become available within the DKRZ jupyterhub after running the `module load climateclaw` command:

<img width="1538" height="650" alt="image" src="https://github.com/user-attachments/assets/3ee46429-9161-41ec-b35a-7813312c5d7d" />


### Removing the extension
Following this guide, running `module load climateclaw` installs some of the dependencies locally and also copies an example jupyter-ai notebook to the user's home directory.
To remove the extension, including all of the dependencies installed during the process, please run the following commands:
```bash
rm -rf ~/.local/lib/python3.12/site-packages/ # deletes local site-packages (system-wide site packages loaded by jupyterhub won't be affected)
rm -rf ~/.local/share/jupyter/jupyter_ai/ # delete jupyter-ai config
rm -rf ~/.local/share/jupyter/labextensions/@jupyter-ai # removes jupyter-ai extension
rm -rf ~/jupyter-ai-examples # removes example notebook directory
```




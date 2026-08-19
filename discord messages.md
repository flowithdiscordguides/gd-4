I'm about to send those 2 apps I've been working on to mod chat, not sure if anyone had a chance to use them, I relaized last week that it was actually not possible for yall to update because of how I set up, so I fixed that, and a lot of other things, and changed the styling, UX and tried to make workflows as smooth as possible, because the main goal is 3 things:
- less clicks to get work done
- reusable resources, so when you. think "I need a clean environment to test these skills or documents", that is what this app is for
- less windows cluttering the screen, gitdesk is a project organizer that combines Finder, github.com, and github desktop that allows you to create sync chains for your projects, 

and app merger allows you to stack vs code windows like web browser tabs, 
it also add some visual customizations to allow you to know when a codex chat is finished, and plays a jingleif you want it to, and can change the jingl to any audio file on your PC

git desk also has notification and jingle features also

they also aim to save diskspace by moving dependencies instead of copying them, so if you are building a rust app, and the dependencies are 4gb, if you make a new version the file size will only be 4gb, not 8gb like duplicating and manually deleting the old folders

allows you to setup sync ignore like gitignore, so if there are files you don't want to ever leave your local project and be added to github, then you can do that, you can also have it so when you sync your private github repo to your public repo, the public repo will only contain the release binaries, not the actual source code, so the source code can stay in your private github organizations, but still allow you to release the app for users to use and update from public repo

I really put a lot of time and love into this because I really think this can save a lot screen clutter, time and cost if you are using AI to manage all these task it could save you $20-100 or more a week in API cost for reasoning and execution cost, which are about 5-60 cents per task, 

and to also show a lot of features I think both Flowith Canvas and Matrix can beefit from,because it's a lot easier to show and use than it is to read

oh and can do local backups for all projects and media to any folder you want

---

earlier messages:

---

Its a project management app. Combines and removes a lot of repetitive task and screen clutter for making local repos and adding them as github projects. So instead of having multiple finder tabs or windows + github desktop + github.com to monitor builds and workflows. The app can contain all of that in one place and set up sync chain between your folders. 

It does not have AI, but also allows you to create skills and documents and add them automatically to your projects for AI. 

So removes the screen and mental clutter from the processes

so I get inspiration, I want to create a project to see if my imagination can be reality, I have to
- open finder
- navigate to my projects folder
- create the folder
- create a new tab in finder
- navigate to my agent skills folder
- copy skills from agent folder and paste them in new folder from step 3
- then use vs code and codex, Neo or image models and canvas, or matrix (requires more steps but  essentially the same steps bellow)
- then the app gets to the point where I feel the model has implemented everything I asked for, so I need to create a new version folder for the work so that way I have a clean backup in case future model breaks the code too much in new features, then I have a manual rollback point
- then I have to repeat steps 7 and 8 again for the new version to add the new features to start with a clean chat so that way the context and state are clean and not drifted from previous chat and folder
- eventually this code is working pretty good now where I don't need to refine and implement as much new features, but opening vs code gets annoying just to run a command
- so usually I will put the project on github if it is a webapp so I can bookmark the app and just easily open it

so this requires more steps:
- create folder for github repo clone
- clone the repo
- push and merge changes
- if it buillds a binary like exe, dmg, or app image then you have to add a tag, push that commit, then watch the action tab to make sure no errors are present
- then if the build suceeds you have to push the release
- so this requires more manaul work because I have the local folder for testing and use the github repo as clean code version, so more copy and pasting files

the DMG does basically 99% of all that in the app
with minimal button presses
for the github stuff normally it would require: vs code (or terminal), github desktop, and github website, which is 300mb of ram
the app does it all for 60 mb of ram
so for the local project part most of that lives on this single screen

you can 
- create project
- create feature
- create version

only have to tyope what you want it to be like 

new project: Golf Game
it will automatically create the first feature 01 init and version 01 init 
then say you are happy with version 1 and want to add a new feature to create a new version backup, you just click the new version buttonand it will auto add 02 for you, so all you have to type is something like "add background npcs" and it will automatically create v02 add background npcs 

also when you build things like node projects or if you build with rust then your dependency folders can be large, if you just copy your folders you double that size which is not good, so the app allows you to check folders to move instead of copy, so that way the file size only duplicates fron text files, so kilobites or mb, instead of 100mb-4gb in each folder


then all the github stuff from above is built in also in the Repo mode, requires your github token PAT and will give you a link to open with permissions already added before creation

so I it has been saving me a lot of time and screen and mental clutter and I was hoping it could help yall and the devs out also with saving time and clutter and saving time on a lot of repetitive tasks
oh, and the sync chain to help you automate this:
> so this requires more manaul work because I have the local folder for testing and use the github repo as clean code version, so more copy and pasting files

PATs are stored in keychain, and if you have a GIhub organization, that requires it's own PAT, but the regular account can still set up a sync chain for the organization repo

then when you want to make a new project you can add parent folders to a favorite list so that way you don't have to open finder every time and it wil automatically add the files there for you, and you can select skills or documents added from user settings to your clean project, so it is primed with skills and context for the model and all you have to do is prompt it
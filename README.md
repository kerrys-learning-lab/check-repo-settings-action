# check-repo-settings-action
Queries a repository to verify (assert) the repository's settings match the desired settings specified via YAML

## Run locally

```
user@host:~ $ docker build -t local/check-repo-settings-action:test .
...
...
...
user@host:~ $ docker run --rm \
                         -it \
                         -e GITHUB_REPOSITORY=kerrys-learning-lab/<repo-name> \
                         -e INPUT_GITHUB_TOKEN=<token> \
                         local/check-repo-settings-action:test
2023-01-31 18:01:47 DEBUG    Using settings from /etc/repository-settings/default-repository-settings.yaml      main.py:126
                    INFO     Checking repository:  (carbernetes)                                                main.py:233
                    DEBUG    Querying https://api.github.com/repos/carbernetes/                                 main.py:256
2023-01-31 18:01:48 DEBUG    Querying https://api.github.com/repos/carbernetes//actions/permissions             main.py:256
                    DEBUG    Querying https://api.github.com/repos/carbernetes//actions/permissions/workflow    main.py:256
                    DEBUG    Querying https://api.github.com/repos/carbernetes//branches/main/protection        main.py:256
2023-01-31 18:01:49 DEBUG    Querying https://api.github.com/repos/carbernetes//branches/main/protection        main.py:256
                    DEBUG    Querying https://api.github.com/repos/carbernetes//tags/protection                 main.py:256
                    DEBUG    Querying https://api.github.com/repos/carbernetes//dependabot/alerts               main.py:256
Validating settings for repository ''... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Test                                                                                                   ┃ Result     ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ Ensure repository settings                                                                             │ ERROR      │
│ Ensure Actions permissions                                                                             │ ERROR      │
│    - Settings >> Actions >> General >> Actions permissions >> Allow all actions and reusable workflows │            │
│ Ensure Workflow permissions                                                                            │ ERROR      │
│    - Settings >> Actions >> General >> Workflow permissions >> Read and write permissions              │            │
│ Ensure 'main' is protected                                                                             │ ERROR      │
│ Ensure 'main' protection settings                                                                      │ ERROR      │
│ Ensure tag patterns are protected                                                                      │ ERROR      │
│    - Settings >> Tags                                                                                  │            │
│ Ensure Dependabot alerts are enabled                                                                   │ ERROR      │
│    - Settings >> Code security and analysis >> Dependabot alerts                                       │            │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┴────────────┘

```

# hls-getlinkable-issue
This is a minimal reproducer for an error I get when using HLS in VSCode on `clash-prelude`:

```
(GetLinkable,NormalizedFilePath "/home/martijn/code/clash-compiler/clash-prelude/src/Clash/XException.hs-boot")called GetLinkable for a file without a linkable: NormalizedFilePath "/home/martijn/code/clash-compiler/clash-prelude/src/Clash/XException.hs-boot"
```

Then open a Nix shell to get a Python environment with `pygls` + `lsprotocol`:

```
nix develop
```

Confirm GHC can compile the project:

```
cabal build
```

Trigger the bug in HLS:

```
./repro.py
```

The test is a bit flaky and it seems to cache results. I've therefore included a script that runs the repro in a temporary directory:

```
./repro-isolated.sh
```

I'm not convinced the reproducer is as small as it can be, but making it smaller triggers [a GHC bug](https://gitlab.haskell.org/ghc/ghc/-/issues/27214).

## Environment
```
$ ghc --version
The Glorious Glasgow Haskell Compilation System, version 9.10.3

$ haskell-language-server-wrapper --version
haskell-language-server version: 2.13.0.0 (GHC: 9.10.3) (PATH: /nix/store/sl99g4kdacsxda9yia2472d7vl625jia-haskell-language-server-2.13.0.0/bin/haskell-language-server-wrapper)

$ cabal --version
cabal-install version 3.16.1.0 
compiled using version 3.16.1.0 of the Cabal library (in-tree)
```

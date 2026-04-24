{
  description = "HLS hs-boot GetLinkable reproducer";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python3.withPackages (ps: [
          ps.pygls
          ps.lsprotocol
          ps.coloredlogs
        ]);
      in {
        devShells.default = pkgs.mkShell {
          packages = [ python pkgs.gmp pkgs.ghc pkgs.cabal-install pkgs.haskell-language-server ];
        };
      });
}

#!/usr/bin/env python3
import asyncio
import logging
import os
import pathlib
import sys

import coloredlogs
from lsprotocol import types as t
from pygls.lsp.client import LanguageClient

ROOT = pathlib.Path(__file__).resolve().parent
TARGET = ROOT / "src" / "Clash" / "Promoted" / "Nat.hs"
HLS = os.environ.get("HLS", "haskell-language-server-wrapper")
CRASH_MARKERS = ("GetLinkable", "without a linkable")

log = logging.getLogger("repro")
hls_log = logging.getLogger("hls")


async def watch_stderr(
    stream: asyncio.StreamReader, cradle_ready: asyncio.Event, crashed: asyncio.Event
) -> None:
    while True:
        line = await stream.readline()
        if not line:
            return
        s = line.decode("utf-8", errors="replace").rstrip()
        if any(m in s for m in CRASH_MARKERS):
            hls_log.error(s)
            crashed.set()
        else:
            hls_log.info(s)
        if "Making new HscEnv" in s:
            cradle_ready.set()


async def main() -> int:
    client = LanguageClient("hls-repro", "0.1")
    cradle_ready = asyncio.Event()
    crashed = asyncio.Event()

    @client.feature(t.WORKSPACE_CONFIGURATION)
    def _config(params: t.ConfigurationParams):
        return [{} for _ in params.items]

    @client.feature(t.CLIENT_REGISTER_CAPABILITY)
    def _register(_params):
        return None

    @client.feature(t.WINDOW_WORK_DONE_PROGRESS_CREATE)
    def _progress(_params):
        return None

    @client.feature(t.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
    def _diagnostics(params: t.PublishDiagnosticsParams):
        for d in params.diagnostics:
            if any(m in d.message for m in CRASH_MARKERS):
                hls_log.error("DIAGNOSTIC on %s: %s", params.uri, d.message[:400])
                crashed.set()
            else:
                hls_log.info("DIAGNOSTIC on %s: %s", params.uri, d.message[:400])

    await client.start_io(HLS, "--lsp")
    asyncio.create_task(watch_stderr(client._server.stderr, cradle_ready, crashed))

    root_uri = ROOT.as_uri()
    await client.initialize_async(
        t.InitializeParams(
            process_id=os.getpid(),
            root_uri=root_uri,
            workspace_folders=[t.WorkspaceFolder(uri=root_uri, name="repro")],
            capabilities=t.ClientCapabilities(
                workspace=t.WorkspaceClientCapabilities(
                    apply_edit=True,
                    workspace_folders=True,
                    configuration=True,
                ),
                text_document=t.TextDocumentClientCapabilities(
                    synchronization=t.TextDocumentSyncClientCapabilities(
                        dynamic_registration=True,
                        did_save=True,
                    ),
                    publish_diagnostics=t.PublishDiagnosticsClientCapabilities(
                        related_information=True,
                    ),
                    code_action=t.CodeActionClientCapabilities(
                        dynamic_registration=True,
                        code_action_literal_support=t.ClientCodeActionLiteralOptions(
                            code_action_kind=t.ClientCodeActionKindOptions(
                                value_set=[
                                    t.CodeActionKind(""),
                                    t.CodeActionKind.QuickFix,
                                    t.CodeActionKind.Refactor,
                                ],
                            ),
                        ),
                    ),
                    document_symbol=t.DocumentSymbolClientCapabilities(
                        dynamic_registration=True,
                        symbol_kind=t.ClientSymbolKindOptions(
                            value_set=[t.SymbolKind(i) for i in range(1, 27)],
                        ),
                        hierarchical_document_symbol_support=True,
                    ),
                    inlay_hint=t.InlayHintClientCapabilities(dynamic_registration=True),
                    code_lens=t.CodeLensClientCapabilities(dynamic_registration=True),
                    folding_range=t.FoldingRangeClientCapabilities(
                        dynamic_registration=True
                    ),
                    semantic_tokens=t.SemanticTokensClientCapabilities(
                        dynamic_registration=True,
                        requests=t.ClientSemanticTokensRequestOptions(
                            range=True,
                            full=t.ClientSemanticTokensRequestFullDelta(delta=True),
                        ),
                        token_types=[],
                        token_modifiers=[],
                        formats=[t.TokenFormat.Relative],
                    ),
                ),
            ),
        )
    )
    client.initialized(t.InitializedParams())

    text = TARGET.read_text()
    uri = TARGET.as_uri()
    log.info("didOpen %s", TARGET)
    client.text_document_did_open(
        t.DidOpenTextDocumentParams(
            text_document=t.TextDocumentItem(
                uri=uri,
                language_id="haskell",
                version=1,
                text=text,
            ),
        )
    )

    log.info("Waiting for cradle...")
    try:
        await asyncio.wait_for(cradle_ready.wait(), timeout=120)
    except asyncio.TimeoutError:
        log.error("Cradle never became ready; aborting.")
        return 1

    # Mirror VSCode's burst of follow-up requests.
    zero = t.Position(line=0, character=0)
    full_range = t.Range(start=zero, end=zero)
    doc = t.TextDocumentIdentifier(uri=uri)

    code_action = asyncio.create_task(
        client.text_document_code_action_async(
            t.CodeActionParams(
                text_document=doc,
                range=full_range,
                context=t.CodeActionContext(
                    diagnostics=[], trigger_kind=t.CodeActionTriggerKind.Automatic
                ),
            )
        )
    )
    asyncio.create_task(
        client.text_document_document_symbol_async(
            t.DocumentSymbolParams(text_document=doc)
        )
    )
    asyncio.create_task(
        client.text_document_inlay_hint_async(
            t.InlayHintParams(
                text_document=doc,
                range=t.Range(start=zero, end=t.Position(line=50, character=0)),
            )
        )
    )
    code_action.cancel()
    asyncio.create_task(
        client.text_document_code_lens_async(t.CodeLensParams(text_document=doc))
    )
    asyncio.create_task(
        client.text_document_folding_range_async(
            t.FoldingRangeParams(text_document=doc)
        )
    )

    log.info("Waiting up to 30s for diagnostic...")
    try:
        await asyncio.wait_for(crashed.wait(), timeout=30)
    except asyncio.TimeoutError:
        pass

    if crashed.is_set():
        log.info("REPRODUCED the GetLinkable bug.")
        rc = 0
    elif client._server.returncode is not None:
        log.error(
            "HLS exited with code %d (no crash observed).", client._server.returncode
        )
        rc = 1
    else:
        log.error("Timed out without reproducing.")
        rc = 1

    try:
        await asyncio.wait_for(client.shutdown_async(None), timeout=5)
        client.exit(None)
        await asyncio.wait_for(client._server.wait(), timeout=5)
    except Exception:
        if client._server.returncode is None:
            client._server.kill()
    return rc


if __name__ == "__main__":
    coloredlogs.install(
        level="INFO",
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        field_styles={
            "asctime": {"color": "green"},
            "levelname": {"bold": True},
            "name": {"color": "cyan"},
        },
    )
    sys.exit(asyncio.run(main()))

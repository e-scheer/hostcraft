// Bundle Monaco locally (offline-capable) and wire its web workers via Vite's
// ?worker import. Without this, the @guolao loader would fetch Monaco from a
// CDN at runtime, which breaks self-hosting.

import * as monaco from 'monaco-editor'
import { loader } from '@guolao/vue-monaco-editor'

import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import JsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker'
import CssWorker from 'monaco-editor/esm/vs/language/css/css.worker?worker'
import HtmlWorker from 'monaco-editor/esm/vs/language/html/html.worker?worker'
import TsWorker from 'monaco-editor/esm/vs/language/typescript/ts.worker?worker'

self.MonacoEnvironment = {
  getWorker(_, label) {
    switch (label) {
      case 'json':
        return new JsonWorker()
      case 'css':
      case 'scss':
      case 'less':
        return new CssWorker()
      case 'html':
      case 'handlebars':
      case 'razor':
        return new HtmlWorker()
      case 'typescript':
      case 'javascript':
        return new TsWorker()
      default:
        return new EditorWorker()
    }
  },
}

// Tell @guolao/vue-monaco-editor to use the locally bundled monaco instead of
// loading it from a CDN at runtime.
loader.config({ monaco })

# Civitas subject

`package/` is the tree topology of the Civitas app from [ios-modularization-benchmark](https://github.com/karthikbedre/ios-modularization-benchmark) at commit `335624f4a6dc`: the generated `approach-tree/Modules` sources, with a `Package.swift` written from the same module list as its Tuist manifest (20 modules, 17 test targets).

Two changes from the original, both so it builds with `swift build` on macOS:

- Library targets are rooted at `Modules/<Name>` with `sources: ["Sources"]`, so each keeps its `Resources` folder, read through SwiftPM's `Bundle.module` instead of Tuist's generated accessor.
- `Modules/DesignSystem/Sources/MacOSShims.swift` adds no-op stand-ins for the few iOS-only SwiftUI modifiers and types the app uses (`navigationBarTitleDisplayMode`, `keyboardType`, `textInputAutocapitalization`, `topBarLeading`, `topBarTrailing`, `UIImage`, `secondarySystemBackground`). No benchmark edit touches it.

`scripts/make-civitas.py` turns this into a git history with one commit per catalogue edit. See [docs/method.md](../../docs/method.md), "Controlled subject: Civitas".

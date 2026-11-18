// The Civitas app targets iOS. This benchmark builds it for macOS so `swift test` and Bazel's macOS
// rules can run it. These no-op stand-ins cover the few iOS-only SwiftUI modifiers the app uses.
// Benchmark edits never touch this file.
#if os(macOS)
import AppKit
import SwiftUI

public enum NavigationBarItem {
    public enum TitleDisplayMode: Sendable { case automatic, inline, large }
}

public enum UIKeyboardType: Sendable { case `default`, emailAddress, numberPad, phonePad, decimalPad, URL }

public typealias UIImage = NSImage

public extension NSImage {
    convenience init(cgImage: CGImage) { self.init(cgImage: cgImage, size: .zero) }
}

public extension NSColor {
    static var secondarySystemBackground: NSColor { .controlBackgroundColor }
}

public extension Image {
    init(uiImage: NSImage) { self.init(nsImage: uiImage) }
}

public struct AutocapitalizationShim: Sendable {
    public static let never = AutocapitalizationShim()
    public static let words = AutocapitalizationShim()
    public static let sentences = AutocapitalizationShim()
    public static let characters = AutocapitalizationShim()
}

public extension ToolbarItemPlacement {
    static var topBarLeading: ToolbarItemPlacement { .navigation }
    static var topBarTrailing: ToolbarItemPlacement { .primaryAction }
}

public extension View {
    func navigationBarTitleDisplayMode(_ mode: NavigationBarItem.TitleDisplayMode) -> some View { self }
    func textInputAutocapitalization(_ style: AutocapitalizationShim?) -> some View { self }
    func keyboardType(_ type: UIKeyboardType) -> some View { self }
}
#endif

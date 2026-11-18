public protocol Formatter: CustomStringConvertible {
    var fields: [String] { get }
}

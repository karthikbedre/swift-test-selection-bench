import Core

public struct Invoice: Formatter {
    public let number: String
    public let total: Int

    public init(number: String, total: Int) {
        self.number = number
        self.total = total
    }

    public var fields: [String] { [number, String(total)] }
}

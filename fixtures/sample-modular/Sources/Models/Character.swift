public struct Character: Equatable, Sendable {
    public let id: Int
    public var name: String

    public init(id: Int, name: String) {
        self.id = id
        self.name = name
    }

    /// Shown in list rows.
    public var displayName: String {
        "\(name) #\(id)"
    }
}

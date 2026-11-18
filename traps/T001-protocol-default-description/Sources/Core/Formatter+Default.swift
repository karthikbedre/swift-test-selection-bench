extension Formatter {
    public var description: String {
        fields.joined(separator: " | ")
    }
}

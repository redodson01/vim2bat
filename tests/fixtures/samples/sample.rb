# A small Ruby file for vim2bat's tests.
module Greeting
  DEFAULT = "world".freeze

  class Greeter
    def initialize(name = DEFAULT)
      @name = name
    end

    def greet(times: 1)
      Array.new(times) { "Hello, #{@name}!" }.join(" ")
    end
  end
end

puts Greeting::Greeter.new(:everyone).greet(times: 2) if __FILE__ == $PROGRAM_NAME
